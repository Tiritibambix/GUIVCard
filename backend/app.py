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
        client = get_carddav_client()
        principal = client.principal()
        collections = principal.calendars()
        address_books = [c for c in collections if "addressbook" in c.get_supported_components()]
        
        if not address_books:
            raise Exception("No address books available")
            
        status = {
            'is_healthy': True,
            'carddav_url': CARDDAV_URL,
            'address_books': len(address_books)
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
    try:
        client = caldav.DAVClient(
            url=CARDDAV_URL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD
        )
        # Test connection
        principal = client.principal()
        collections = principal.calendars()
        address_books = [c for c in collections if "addressbook" in c.get_supported_components()]
        logger.info(f"Connected to CardDAV server, found {len(address_books)} address books")
        return client
    except Exception as e:
        logger.error(f"Error connecting to CardDAV server: {str(e)}")
        raise

@app.route('/contacts', methods=['GET', 'POST'])
@check_login_required
def contacts():
    try:
        client = get_carddav_client()
        principal = client.principal()
        collections = principal.calendars()
        address_books = [c for c in collections if "addressbook" in c.get_supported_components()]
        
        if not address_books:
            logger.error("No address books found")
            flash("Error: No address books available")
            return render_template('index.html', contacts=[])
        
        abook = address_books[0]
        
        if request.method == 'POST':
            try:
                # Create new contact
                vcard = vobject.vCard()
                vcard.add('fn').value = request.form['name']
                vcard.add('email').value = request.form['email']
                if request.form.get('phone'):
                    vcard.add('tel').value = request.form['phone']
                
                # Save the vcard to the address book
                abook.add_vcard(vcard.serialize())
                flash('Contact created successfully')
                return redirect(url_for('contacts'))
            except Exception as e:
                logger.error(f"Error creating contact: {str(e)}")
                flash(f"Error creating contact: {str(e)}")
                return redirect(url_for('contacts'))
        
        # GET: List contacts
        contacts = []
        # Use search() without parameters to get all vcards
        for card in abook.search():
            vobj = card.vobject_instance
            contacts.append({
                'id': card.uid,
                'name': vobj.fn.value,
                'email': vobj.email.value if hasattr(vobj, 'email') else '',
                'phone': vobj.tel.value if hasattr(vobj, 'tel') else ''
            })
        return render_template('index.html', contacts=contacts)
        
    except Exception as e:
        logger.error(f"Error accessing contacts: {str(e)}")
        flash(f"Error: {str(e)}")
        return render_template('index.html', contacts=[])

@app.route('/contacts/update', methods=['POST'])
@check_login_required
def update_contact():
    try:
        client = get_carddav_client()
        principal = client.principal()
        collections = principal.calendars()
        address_books = [c for c in collections if "addressbook" in c.get_supported_components()]
        
        if not address_books:
            raise Exception("No address books available")
        abook = address_books[0]
        
        contact_id = request.form['contact_id']
        vcard = next(abook.search(uid=contact_id))
        
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
        
        # Update the vcard in the address book
        card_data = vcard_obj.serialize()
        vcard.set_vcard_data(card_data)
        vcard.save()
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
        collections = principal.calendars()
        address_books = [c for c in collections if "addressbook" in c.get_supported_components()]
        
        if not address_books:
            raise Exception("No address books available")
        abook = address_books[0]
        vcard = next(abook.search(uid=contact_id))
        vcard.delete()
        flash('Contact deleted successfully')
        return redirect(url_for('contacts'))
    except Exception as e:
        logger.error(f"Error deleting contact: {str(e)}")
        flash(f"Error deleting contact: {str(e)}")
        return redirect(url_for('contacts'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')