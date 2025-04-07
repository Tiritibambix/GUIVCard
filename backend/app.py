from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import os
import carddav
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
        # TODO: Implement CardDAV client connection and contact fetching
        return jsonify({"message": "Contact fetching not implemented yet"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts', methods=['POST'])
@require_auth
def create_contact():
    try:
        # TODO: Implement contact creation
        return jsonify({"message": "Contact creation not implemented yet"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts/<contact_id>', methods=['PUT'])
@require_auth
def update_contact(contact_id):
    try:
        # TODO: Implement contact update
        return jsonify({"message": "Contact update not implemented yet"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/contacts/<contact_id>', methods=['DELETE'])
@require_auth
def delete_contact(contact_id):
    try:
        # TODO: Implement contact deletion
        return jsonify({"message": "Contact deletion not implemented yet"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')