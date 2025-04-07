from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import os
import caldav
import vobject
from werkzeug.security import check_password_hash

app = Flask(__name__)
CORS(app)

# Configuration from environment variables
CARDDAV_URL = os.environ['CARDDAV_URL']
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD_HASH = os.environ['ADMIN_PASSWORD_HASH']
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', 'http://localhost:8190')

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
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"message": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated

def check_auth(username, password):
    if not username or not password:
        return False
    return username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/api/contacts', methods=['GET'])
@require_auth
def get_contacts():
    try:
        client = caldav.DAVClient(url=CARDDAV_URL)
        principal = client.principal()
        address_books = principal.addressbooks()
        
        if not address_books:
            return jsonify({"message": "No address books found"}), 404
            
        contacts = []
        for abook in address_books:
            for card in abook.get_all_vcards():
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
                
        return jsonify(contacts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts', methods=['POST'])
@require_auth
def create_contact():
    try:
        data = request.json
        client = caldav.DAVClient(url=CARDDAV_URL)
        principal = client.principal()
        address_books = principal.addressbooks()
        
        if not address_books:
            return jsonify({"message": "No address books found"}), 404
            
        address_book = address_books[0]  # Use first address book
        
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
            
        # Save vCard
        address_book.add_vcard(vcard=vcard.serialize())
        return jsonify({"message": "Contact created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts/<contact_id>', methods=['PUT'])
@require_auth
def update_contact(contact_id):
    try:
        data = request.json
        client = caldav.DAVClient(url=CARDDAV_URL)
        principal = client.principal()
        address_books = principal.addressbooks()
        
        if not address_books:
            return jsonify({"message": "No address books found"}), 404
            
        # Find contact in address books
        for abook in address_books:
            try:
                card = abook.get_vcard(contact_id)
                vcard = vobject.readOne(card)
                
                # Update fields
                vcard.fn.value = data['fullName']
                if data.get('email'):
                    if hasattr(vcard, 'email'):
                        vcard.email.value = data['email']
                    else:
                        vcard.add('email').value = data['email']
                if data.get('phone'):
                    if hasattr(vcard, 'tel'):
                        vcard.tel.value = data['phone']
                    else:
                        vcard.add('tel').value = data['phone']
                if data.get('organization'):
                    if hasattr(vcard, 'org'):
                        vcard.org.value = [data['organization']]
                    else:
                        vcard.add('org').value = [data['organization']]
                if data.get('title'):
                    if hasattr(vcard, 'title'):
                        vcard.title.value = data['title']
                    else:
                        vcard.add('title').value = data['title']
                if data.get('notes'):
                    if hasattr(vcard, 'note'):
                        vcard.note.value = data['notes']
                    else:
                        vcard.add('note').value = data['notes']
                
                # Save updated vCard
                card.set_vcard(vcard.serialize())
                return jsonify({"message": "Contact updated successfully"}), 200
            except caldav.error.NotFoundError:
                continue
                
        return jsonify({"message": "Contact not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts/<contact_id>', methods=['DELETE'])
@require_auth
def delete_contact(contact_id):
    try:
        client = caldav.DAVClient(url=CARDDAV_URL)
        principal = client.principal()
        address_books = principal.addressbooks()
        
        if not address_books:
            return jsonify({"message": "No address books found"}), 404
            
        # Find and delete contact in address books
        for abook in address_books:
            try:
                card = abook.get_vcard(contact_id)
                card.delete()
                return jsonify({"message": "Contact deleted successfully"}), 200
            except caldav.error.NotFoundError:
                continue
                
        return jsonify({"message": "Contact not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')