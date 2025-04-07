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
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('guivcard')

# Enable info logging for requests and caldav
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('caldav').setLevel(logging.INFO)

app = Flask(__name__)

# Configuration from environment variables
CARDDAV_URL = os.environ['CARDDAV_URL']
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', 'http://localhost:8190')

# Parse CORS origins
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGIN.split(',')]
logger.info(f"Starting GuiVCard backend with CORS origins: {CORS_ORIGINS}")
logger.info(f"CardDAV URL: {CARDDAV_URL}")

# Configure CORS
CORS(app,
    resources={
        r"/api/*": {
            "origins": CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type"],
            "expose_headers": ["Authorization"],
            "supports_credentials": True,
            "max_age": 3600
        }
    },
    allow_credentials=True
)

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    if request.method == 'OPTIONS':
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
    return response

# Test CardDAV connection at startup
try:
    auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'User-Agent': 'GuiVCard/1.0',
        'Depth': '1'
    }
    
    response = requests.request('PROPFIND', CARDDAV_URL, headers=headers)
    logger.info(f"CardDAV test status: {response.status_code}")
    
    if response.status_code == 207:
        logger.info("Successfully connected to CardDAV server")
    else:
        logger.error(f"Unexpected response from server: {response.status_code}")
        
except Exception as e:
    logger.error(f"Failed to test CardDAV server: {str(e)}")

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

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response

    # Only require auth for GET requests
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return jsonify({"message": "Authentication required"}), 401
    logger.info("Health check endpoint called")
    try:
        auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_header}',
            'User-Agent': 'GuiVCard/1.0',
            'Depth': '1'
        }
        response = requests.request('PROPFIND', CARDDAV_URL, headers=headers, timeout=5)
        
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
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "error",
            "cardDAV": "error",
            "error": str(e)
        }), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')