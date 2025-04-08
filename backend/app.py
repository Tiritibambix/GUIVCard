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

# Verify CardDAV URL format at startup
try:
    parsed = urlparse(CARDDAV_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid CardDAV URL format")
        
    # Test connection
    auth_header = base64.b64encode(f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'User-Agent': 'GuiVCard/1.0',
        'Depth': '1'
    }
    
    response = requests.request('PROPFIND', CARDDAV_URL, headers=headers)
    logger.info(f"CardDAV test status: {response.status_code}")
    
    if response.status_code == 207:
        logger.info(f"Successfully connected to CardDAV server at {CARDDAV_URL}")
    else:
        logger.error(f"Unexpected response from server: {response.status_code}")
        
except Exception as e:
    logger.error(f"Failed to connect to CardDAV server: {str(e)}")
    logger.error(f"Please verify your CardDAV URL: {CARDDAV_URL}")

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
        client, abook = get_carddav_client()
            
        # Verify we can access the address book by listing contacts
        next(abook.date_search(), None)  # Try to get first contact, None if empty
            
        status = {
            'is_healthy': True,
            'carddav_url': str(abook.url),
            'message': 'Successfully connected to address book'
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
    """Get CardDAV client and address book"""
    try:
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD
        )
        principal = client.principal()
        logger.info("Connected to CardDAV server")

        addressbooks = principal.addressbooks()
        if not addressbooks:
            raise Exception("No address book found")
        
        # Use first available address book
        abook = addressbooks[0]
        logger.info(f"Using address book: {abook.url}")

        # Store reference for convenience
        client.addressbook = abook
        return client, abook
        
    except Exception as e:
        logger.error(f"Error connecting to CardDAV server: {str(e)}")
        raise Exception(f"Could not access address book - {str(e)}")

@app.route('/contacts', methods=['GET', 'POST'])
@check_login_required
def contacts():
    try:
        client, abook = get_carddav_client()
        
        if request.method == 'POST':
            try:
                # Create new contact as pure vCard string
                vcard_content = f"""BEGIN:VCARD
VERSION:3.0
FN:{request.form['name']}
EMAIL:{request.form['email']}
{f'TEL:{request.form["phone"]}' if request.form.get('phone') else ''}
END:VCARD"""
                
                # Save directly to address book
                abook.save_vcard(vcard_content)
                flash('Contact created successfully')
                return redirect(url_for('contacts'))
            except Exception as e:
                logger.error(f"Error creating contact: {str(e)}")
                flash(f"Error creating contact: {str(e)}")
                return redirect(url_for('contacts'))
        
        # GET: List contacts
        contacts = []
        # Use search() without parameters to get all vcards
        # List all items in collection
        for item in abook.date_search():
            try:
                vcard_data = vobject.readOne(item.data)
                if not hasattr(vcard_data, 'fn'):
                    logger.warning(f"Skipping contact without FN: {item.url}")
                    continue
                    
                # Use the last part of the URL as ID
                href = item.url.path.split('/')[-1]
                
                contacts.append({
                    'id': href,
                    'name': vcard_data.fn.value,
                    'email': vcard_data.email.value if hasattr(vcard_data, 'email') else '',
                    'phone': vcard_data.tel.value if hasattr(vcard_data, 'tel') else ''
                })
            except Exception as card_error:
                logger.warning(f"Error processing contact: {card_error}")
                continue
        return render_template('index.html', contacts=contacts)
        
    except Exception as e:
        logger.error(f"Error accessing contacts: {str(e)}")
        flash(f"Error: {str(e)}")
        return render_template('index.html', contacts=[])

@app.route('/contacts/update', methods=['POST'])
@check_login_required
def update_contact():
    try:
        client, abook = get_carddav_client()
        
        contact_id = request.form['contact_id']
        # Find contact by ID
        found_item = None
        for item in abook.date_search():
            if contact_id in item.url.path:
                found_item = item
                break
                
        if not found_item:
            raise Exception("Contact not found")
        
        # Create new vCard
        new_vcard = vobject.vCard()
        new_vcard.add('fn').value = request.form['name']
        new_vcard.add('email').value = request.form['email']
        if request.form.get('phone'):
            new_vcard.add('tel').value = request.form['phone']
        
        # Update the contact
        found_item.put(new_vcard.serialize(), content_type='text/vcard')
        flash('Contact updated successfully')
    except Exception as e:
        logger.error(f"Error updating contact: {str(e)}")
        flash(f"Error updating contact: {str(e)}")
    
    return redirect(url_for('contacts'))

@app.route('/contacts/<contact_id>/delete', methods=['POST'])
@check_login_required
def delete_contact(contact_id):
    try:
        client, abook = get_carddav_client()
        
        # Find contact by ID
        found_item = None
        for item in abook.date_search():
            if contact_id in item.url.path:
                found_item = item
                break
                
        if not found_item:
            raise Exception("Contact not found")
            
        # Delete the contact
        found_item.delete()
        flash('Contact deleted successfully')
        return redirect(url_for('contacts'))
    except Exception as e:
        logger.error(f"Error deleting contact: {str(e)}")
        flash(f"Error deleting contact: {str(e)}")
        return redirect(url_for('contacts'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')