from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import os
import caldav
import vobject
import logging
import sys
import requests
from urllib.parse import urlparse
import base64

# Configure logging to write to stdout
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('guivcard')

# Enable debug logging for requests and caldav
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('caldav').setLevel(logging.INFO)

app = Flask(__name__)
CORS(app)

# Configuration from environment variables
CARDDAV_URL = os.environ['CARDDAV_URL']
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', ['http://localhost:8195', 'http://localhost:80', 'http://localhost'])

logger.info(f"Starting GuiVCard backend with CORS_ORIGIN: {CORS_ORIGIN}")
logger.info(f"CardDAV URL: {CARDDAV_URL}")

# Test CardDAV connection at startup
try:
    auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'User-Agent': 'GuiVCard/1.0',
        'Depth': '1'
    }
    
    # Test addressbook access with PROPFIND
    response = requests.request('PROPFIND', CARDDAV_URL, headers=headers)
    logger.info(f"PROPFIND response status: {response.status_code}")
    logger.info(f"Address book response headers: {dict(response.headers)}")
    logger.debug(f"Address book response content: {response.content.decode()}")
    
    if response.status_code == 207:
        logger.info("Successfully connected to CardDAV server")
    else:
        logger.error(f"Unexpected response from server: {response.status_code}")

except Exception as e:
    logger.error(f"Failed to test CardDAV server: {str(e)}", exc_info=True)

# Configure CORS
CORS(app, resources={
    r"/api/*": {
        "origins": CORS_ORIGIN if isinstance(CORS_ORIGIN, list) else [CORS_ORIGIN],
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Authorization", "Content-Type"],
        "expose_headers": ["Authorization"],
        "supports_credentials": True
    }
})

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            logger.warning("No authorization header provided")
            return jsonify({"message": "Authentication required"}), 401
        if not check_auth(auth.username, auth.password):
            logger.warning(f"Failed authentication attempt for user: {auth.username}")
            return jsonify({"message": "Authentication failed"}), 401
        logger.info(f"Successful authentication for user: {auth.username}")
        return f(*args, **kwargs)
    return decorated

def check_auth(username, password):
    if not username or not password:
        logger.warning("Missing username or password")
        return False
    result = username == ADMIN_USERNAME and password == ADMIN_PASSWORD
    if not result:
        logger.warning("Invalid credentials provided")
    return result

@app.route('/api/health', methods=['GET'])
@require_auth
def health_check():
    logger.info("Health check endpoint called")
    try:
        # Test CardDAV connection
        auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_header}',
            'User-Agent': 'GuiVCard/1.0',
            'Depth': '1'
        }
        response = requests.request('PROPFIND', CARDDAV_URL, headers=headers)
        
        if response.status_code == 207:
            return jsonify({
                "status": "healthy",
                "cardDAV": "connected"
            }), 200
        else:
            return jsonify({
                "status": "degraded",
                "cardDAV": "error",
                "error": f"CardDAV server returned {response.status_code}"
            }), 503
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "cardDAV": "error",
            "error": str(e)
        }), 503

@app.route('/api/contacts', methods=['GET'])
@require_auth
def get_contacts():
    try:
        logger.debug(f"Creating DAVClient with URL: {CARDDAV_URL}")
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            ssl_verify_cert=True
        )
        logger.info("Successfully created DAVClient")

        # Create an AddressBook object directly without using principal
        address_book = caldav.AddressBook(
            client=client,
            url=CARDDAV_URL
        )
        logger.info(f"Created AddressBook object for URL: {CARDDAV_URL}")

        try:
            logger.debug("Getting all vcards...")
            cards = list(address_book.get_all_vcards())
            logger.info(f"Found {len(cards)} contacts in address book")

            contacts = []
            for card in cards:
                try:
                    logger.debug(f"Processing card: {card.id}")
                    vcard = vobject.readOne(card)
                    contact = {
                        "id": card.id,
                        "fullName": str(vcard.fn.value),
                        "email": str(vcard.email.value) if hasattr(vcard, 'email') else None,
                        "phone": str(vcard.tel.value) if hasattr(vcard, 'tel') else None,
                        "organization": str(vcard.org.value[0]) if hasattr(vcard, 'org') else None,
                        "title": str(vcard.title.value) if hasattr(vcard, 'title') else None,
                        "notes": str(vcard.note.value) if hasattr(vcard, 'note') else None,
                        "lastModified": card.get_etag()
                    }
                    contacts.append(contact)
                    logger.debug(f"Added contact: {contact['fullName']}")
                except Exception as e:
                    logger.error(f"Error processing vCard {card.id}: {str(e)}", exc_info=True)

            logger.info(f"Retrieved {len(contacts)} contacts total")
            return jsonify(contacts), 200

        except Exception as e:
            logger.error(f"Error reading address book: {str(e)}", exc_info=True)
            return jsonify({"error": "Failed to read contacts"}), 500

    except Exception as e:
        error_msg = f"Error getting contacts: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

@app.route('/api/contacts', methods=['POST'])
@require_auth
def create_contact():
    try:
        data = request.json
        if not data or not data.get('fullName'):
            return jsonify({"error": "Full name is required"}), 400

        logger.debug(f"Creating DAVClient for new contact: {data['fullName']}")
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            ssl_verify_cert=True
        )

        address_book = caldav.AddressBook(
            client=client,
            url=CARDDAV_URL
        )

        # Create vCard
        vcard = vobject.vCard()
        vcard.add('fn').value = data['fullName']
        if data.get('email'):
            vcard.add('email').value = data['email']
        if data.get('phone'):
            vcard.add('tel').value = data['phone']
        if data.get('organization'):
            vcard.add('org').value = [data['organization']]
        if data.get('title'):
            vcard.add('title').value = data['title']
        if data.get('notes'):
            vcard.add('note').value = data['notes']

        # Save to server
        card = address_book.save_vcard(vcard.serialize())
        logger.info(f"Successfully created contact: {data['fullName']}")

        # Return the new contact data
        return jsonify({
            "id": card.id,
            "fullName": data['fullName'],
            "email": data.get('email'),
            "phone": data.get('phone'),
            "organization": data.get('organization'),
            "title": data.get('title'),
            "notes": data.get('notes'),
            "lastModified": card.get_etag()
        }), 201

    except Exception as e:
        error_msg = f"Error creating contact: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

@app.route('/api/contacts/<contact_id>', methods=['PUT'])
@require_auth
def update_contact(contact_id):
    try:
        data = request.json
        if not data or not data.get('fullName'):
            return jsonify({"error": "Full name is required"}), 400

        logger.debug(f"Creating DAVClient for updating contact: {contact_id}")
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            ssl_verify_cert=True
        )

        address_book = caldav.AddressBook(
            client=client,
            url=CARDDAV_URL
        )

        # Find the contact
        try:
            card = next(c for c in address_book.get_all_vcards() if c.id == contact_id)
        except StopIteration:
            return jsonify({"error": "Contact not found"}), 404

        # Update vCard
        vcard = vobject.readOne(card)
        vcard.fn.value = data['fullName']
        
        # Update or remove email
        if hasattr(vcard, 'email'):
            if data.get('email'):
                vcard.email.value = data['email']
            else:
                del vcard.email
        elif data.get('email'):
            vcard.add('email').value = data['email']

        # Update or remove phone
        if hasattr(vcard, 'tel'):
            if data.get('phone'):
                vcard.tel.value = data['phone']
            else:
                del vcard.tel
        elif data.get('phone'):
            vcard.add('tel').value = data['phone']

        # Update or remove organization
        if hasattr(vcard, 'org'):
            if data.get('organization'):
                vcard.org.value = [data['organization']]
            else:
                del vcard.org
        elif data.get('organization'):
            vcard.add('org').value = [data['organization']]

        # Update or remove title
        if hasattr(vcard, 'title'):
            if data.get('title'):
                vcard.title.value = data['title']
            else:
                del vcard.title
        elif data.get('title'):
            vcard.add('title').value = data['title']

        # Update or remove notes
        if hasattr(vcard, 'note'):
            if data.get('notes'):
                vcard.note.value = data['notes']
            else:
                del vcard.note
        elif data.get('notes'):
            vcard.add('note').value = data['notes']

        # Save updated vCard
        card.upload(vcard.serialize())
        logger.info(f"Successfully updated contact: {contact_id}")

        # Return updated contact data
        return jsonify({
            "id": card.id,
            "fullName": data['fullName'],
            "email": data.get('email'),
            "phone": data.get('phone'),
            "organization": data.get('organization'),
            "title": data.get('title'),
            "notes": data.get('notes'),
            "lastModified": card.get_etag()
        }), 200

    except Exception as e:
        error_msg = f"Error updating contact: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

@app.route('/api/contacts/<contact_id>', methods=['DELETE'])
@require_auth
def delete_contact(contact_id):
    try:
        logger.debug(f"Creating DAVClient for deleting contact: {contact_id}")
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            ssl_verify_cert=True
        )

        address_book = caldav.AddressBook(
            client=client,
            url=CARDDAV_URL
        )

        # Find and delete the contact
        try:
            card = next(c for c in address_book.get_all_vcards() if c.id == contact_id)
            card.delete()
            logger.info(f"Successfully deleted contact: {contact_id}")
            return '', 204
        except StopIteration:
            return jsonify({"error": "Contact not found"}), 404

    except Exception as e:
        error_msg = f"Error deleting contact: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')