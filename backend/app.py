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
logging.getLogger('urllib3').setLevel(logging.DEBUG)
logging.getLogger('caldav').setLevel(logging.DEBUG)

app = Flask(__name__)
CORS(app)

# Configuration from environment variables
CARDDAV_URL = os.environ['CARDDAV_URL']
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', 'http://localhost:8190')

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
        "origins": CORS_ORIGIN,
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Authorization", "Content-Type"],
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
def health_check():
    logger.info("Health check endpoint called")
    return jsonify({"status": "healthy"}), 200

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

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')