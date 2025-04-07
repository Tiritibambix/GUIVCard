from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
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
app.secret_key = os.urandom(24)  # for session management

# Configuration from environment variables
CARDDAV_URL = os.environ['CARDDAV_URL']
ADMIN_USERNAME = os.environ['ADMIN_USERNAME']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']

logger.info(f"Starting GuiVCard with CardDAV URL: {CARDDAV_URL}")

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('contacts'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if check_auth(username, password):
            session['username'] = username
            return redirect(url_for('contacts'))
        flash('Invalid credentials')
        return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

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

def check_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/health')
@check_login_required
def health_check():
    try:
        auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_header}',
            'User-Agent': 'GuiVCard/1.0',
            'Depth': '1'
        }
        response = requests.request('PROPFIND', CARDDAV_URL, headers=headers, timeout=5)
        
        status = {
            'is_healthy': response.status_code == 207,
            'status_code': response.status_code,
            'carddav_url': CARDDAV_URL
        }
        return render_template('health.html', status=status)
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        status = {
            'is_healthy': False,
            'error': str(e),
            'carddav_url': CARDDAV_URL
        }
        return render_template('health.html', status=status)

def get_carddav_client():
    client = caldav.DAVClient(
        url=CARDDAV_URL,
        username=ADMIN_USERNAME,
        password=ADMIN_PASSWORD
    )
    return client

@app.route('/contacts/<contact_id>', methods=['GET'])
@check_login_required
def get_contact(contact_id):
    try:
        client = get_carddav_client()
        principal = client.principal()
        abook = principal.address_book()
        vcard = abook.get_vcard(contact_id)
        
        contact = {
            'id': contact_id,
            'name': vcard.vobject_instance.fn.value,
            'email': vcard.vobject_instance.email.value if hasattr(vcard.vobject_instance, 'email') else '',
            'phone': vcard.vobject_instance.tel.value if hasattr(vcard.vobject_instance, 'tel') else ''
        }
        return jsonify(contact)
    except Exception as e:
        logger.error(f"Error getting contact: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/contacts', methods=['GET', 'POST'])
@check_login_required
def contacts():
    client = get_carddav_client()
    principal = client.principal()
    abook = principal.address_book()
    
    if request.method == 'POST':
        try:
            # Create new contact
            vcard = vobject.vCard()
            vcard.add('fn').value = request.form['name']
            vcard.add('email').value = request.form['email']
            if request.form.get('phone'):
                vcard.add('tel').value = request.form['phone']
            
            abook.save_vcard(vcard.serialize())
            flash('Contact created successfully')
            return redirect(url_for('contacts'))
        except Exception as e:
            logger.error(f"Error creating contact: {str(e)}")
            flash(f"Error creating contact: {str(e)}")
            return redirect(url_for('contacts'))
    
    # GET: List contacts
    try:
        contacts = []
        for card in abook.get_vcards():
            vcard = card.vobject_instance
            contacts.append({
                'id': card.id,
                'name': vcard.fn.value,
                'email': vcard.email.value if hasattr(vcard, 'email') else '',
                'phone': vcard.tel.value if hasattr(vcard, 'tel') else ''
            })
        return render_template('index.html', contacts=contacts)
    except Exception as e:
        logger.error(f"Error listing contacts: {str(e)}")
        flash(f"Error loading contacts: {str(e)}")
        return render_template('index.html', contacts=[])

@app.route('/contacts/update', methods=['POST'])
@check_login_required
def update_contact():
    try:
        client = get_carddav_client()
        principal = client.principal()
        abook = principal.address_book()
        
        contact_id = request.form['contact_id']
        vcard = abook.get_vcard(contact_id)
        
        # Update contact
        vcard_obj = vcard.vobject_instance
        vcard_obj.fn.value = request.form['name']
        if hasattr(vcard_obj, 'email'):
            vcard_obj.email.value = request.form['email']
        else:
            vcard_obj.add('email').value = request.form['email']
            
        if request.form.get('phone'):
            if hasattr(vcard_obj, 'tel'):
                vcard_obj.tel.value = request.form['phone']
            else:
                vcard_obj.add('tel').value = request.form['phone']
        
        abook.save_vcard(vcard_obj.serialize(), contact_id)
        flash('Contact updated successfully')
    except Exception as e:
        logger.error(f"Error updating contact: {str(e)}")
        flash(f"Error updating contact: {str(e)}")
    
    return redirect(url_for('contacts'))

@app.route('/contacts/<contact_id>/delete', methods=['POST'])
@check_login_required
def delete_contact(contact_id):
    try:
        client = get_carddav_client()
        principal = client.principal()
        abook = principal.address_book()
        vcard = abook.get_vcard(contact_id)
        vcard.delete()
        flash('Contact deleted successfully')
        return redirect(url_for('contacts'))
    except Exception as e:
        logger.error(f"Error deleting contact: {str(e)}")
        flash(f"Error deleting contact: {str(e)}")
        return redirect(url_for('contacts'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')