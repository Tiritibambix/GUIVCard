from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from functools import wraps
import os
import vobject
import logging
import sys
import requests
from urllib.parse import urlparse
import base64
import uuid
from typing import Dict

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
            
        # List contacts to verify access
        response = abook['session'].request('PROPFIND', abook['url'], headers={'Depth': '1'})
        if response.status_code != 207:
            raise Exception("Could not list contacts")
            
        status = {
            'is_healthy': response.status_code == 207,
            'carddav_url': abook['url'],
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
def generate_vcard(data: Dict[str, str]) -> str:
    """Generate a vCard 3.0 from a dictionary of fields."""
    uid = data.get("UID") or str(uuid.uuid4())
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
    ]

    if fn := data.get("FN"):
        lines.append(f"FN:{fn}")

    if data.get("N"):
        n_parts = data["N"].split(" ", 1)
        last = n_parts[0]
        first = n_parts[1] if len(n_parts) > 1 else ""
        lines.append(f"N:{last};{first};;;")

    if org := data.get("ORG"):
        lines.append(f"ORG:{org}")

    if email := data.get("EMAIL"):
        lines.append(f"EMAIL:{email}")

    if tel := data.get("TEL"):
        lines.append(f"TEL:{tel}")

    if adr := data.get("ADR"):
        lines.append(
            f"ADR:;;{adr.get('street','')};{adr.get('city','')};;{adr.get('postal','')};{adr.get('country','')}"
        )

    if url := data.get("URL"):
        lines.append(f"URL:{url}")

    if photo := data.get("PHOTO"):
        photo_b64 = base64.b64encode(photo).decode("utf-8")
        lines.append(f"PHOTO;ENCODING=b;TYPE=JPEG:{photo_b64}")

    if bday := data.get("BDAY"):
        lines.append(f"BDAY:{bday}")

    if note := data.get("NOTE"):
        lines.append(f"NOTE:{note}")

    lines.append(f"UID:{uid}")
    lines.append("END:VCARD")
    lines.append("")  # Final line break

    return "\r\n".join(lines)


def get_carddav_client():
    """Get CardDAV client and address book"""
    try:
        # Create session with authentication
        session = requests.Session()
        session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)
        session.headers.update({
            'User-Agent': 'GuiVCard/1.0',
            'Depth': '0',
            'Accept': 'text/vcard'
        })
        
        # Verify address book access
        response = session.request('PROPFIND', CARDDAV_URL)
        if response.status_code != 207:
            raise Exception(
                f"Failed to access address book: status {response.status_code}\n"
                f"Response: {response.text[:200]}"  # First 200 chars for debug
            )
            
        logger.info(f"Successfully connected to CardDAV server at {CARDDAV_URL}")
        
        # Create a simple object to handle address book operations
        abook = {
            'url': CARDDAV_URL,
            'session': session
        }
        return session, abook

    except Exception as e:
        logger.error(f"Error accessing CardDAV server: {str(e)}")
        raise Exception("Could not access address book - verify URL and credentials")

@app.route('/contacts', methods=['GET', 'POST'])
@check_login_required
def contacts():
    try:
        client, abook = get_carddav_client()
        
        if request.method == 'POST':
            try:
                # Collect all available contact data
                name = request.form.get('name', '').strip()
                vcard_data = {
                    "FN": name,
                    "N": name,  # Will be split into last;first automatically
                    "EMAIL": request.form.get('email', '').strip(),
                }
                
                if phone := request.form.get('phone', '').strip():
                    vcard_data["TEL"] = phone
                    
                if org := request.form.get('organization', '').strip():
                    vcard_data["ORG"] = org
                    
                if note := request.form.get('note', '').strip():
                    vcard_data["NOTE"] = note

                # Generate vCard content
                vcard_content = generate_vcard(vcard_data)
                
                # Validate by parsing
                vobject.readOne(vcard_content)
                logger.info(f"Creating vCard:\n{vcard_content}")

                # Generate a unique filename for the vCard
                filename = f"{base64.urlsafe_b64encode(os.urandom(12)).decode()}.vcf"
                url = f"{abook['url'].rstrip('/')}/{filename}"
                # PUT the new vCard with explicit headers
                logger.info(f"PUT contact to: {url}")
                response = abook['session'].put(
                    url,
                    data=vcard_content,
                    headers={"Content-Type": "text/vcard"}
                )
                
                if response.status_code not in (201, 204):
                    raise Exception(f"Failed to create contact: status {response.status_code}, body: {response.text}")
                
                flash('Contact created successfully')
                return redirect(url_for('contacts'))
            except Exception as e:
                logger.error(f"Error creating contact: {str(e)}")
                flash(f"Error creating contact: {str(e)}")
                return redirect(url_for('contacts'))
        
        # List contacts via PROPFIND
        contacts = []
        # List all contacts with Depth: 1
        response = abook['session'].request(
            'PROPFIND',
            abook['url'],
            headers={'Depth': '1'}  # Override default Depth: 0
        )
        
        if response.status_code == 207:
            logger.info(f"Found contacts in address book: {abook['url']}")
            # Parse XML response
            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.content)
            
            # Process each response element
            for elem in root.findall('.//{DAV:}response'):
                href = elem.find('.//{DAV:}href').text
                if href.endswith('.vcf'):  # Only process vCard files
                    # Get the vCard data
                    card_url = urlparse(CARDDAV_URL).scheme + '://' + urlparse(CARDDAV_URL).netloc + href
                    card_response = abook['session'].get(card_url)
                    if card_response.status_code == 200:
                        try:
                            vcard_data = vobject.readOne(card_response.text)
                            
                            # Get name components
                            fn = getattr(vcard_data, 'fn', None)
                            name = fn.value if fn else "No Name"
                            
                            # Get email (first one if multiple exist)
                            emails = vcard_data.contents.get('email', [])
                            email = emails[0].value if emails else ''
                            
                            # Get phone (first one if multiple exist)
                            tels = vcard_data.contents.get('tel', [])
                            phone = tels[0].value if tels else ''
                            
                            # Get organization
                            orgs = vcard_data.contents.get('org', [])
                            org = orgs[0].value[0] if orgs and orgs[0].value else ''
                            
                            # Get note
                            notes = vcard_data.contents.get('note', [])
                            note = notes[0].value if notes else ''
                            
                            contacts.append({
                                'id': href.split('/')[-1],
                                'name': name,
                                'email': email,
                                'phone': phone,
                                'org': org,
                                'note': note
                            })
                            
                            logger.debug(f"Parsed contact: {name} ({href})")
                        except Exception as e:
                            logger.warning(f"Error parsing vCard {href}: {str(e)}\nContent: {card_response.text[:200]}")
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
        url = f"{abook['url'].rstrip('/')}/{contact_id}"
        
        # Verify contact exists
        response = abook['session'].request('PROPFIND', url, headers={'Depth': '0'})
        if response.status_code != 207:
            raise Exception("Contact not found")
        
        # Collect all contact data for update
        name = request.form.get('name', '').strip()
        vcard_data = {
            "FN": name,
            "N": name,  # Will be split into last;first automatically
            "EMAIL": request.form.get('email', '').strip(),
        }
        
        if phone := request.form.get('phone', '').strip():
            vcard_data["TEL"] = phone
            
        if org := request.form.get('organization', '').strip():
            vcard_data["ORG"] = org
            
        if note := request.form.get('note', '').strip():
            vcard_data["NOTE"] = note

        # Generate and validate vCard content
        vcard_content = generate_vcard(vcard_data)
        
        logger.info(f"Updating vCard at {url}:\n{vcard_content}")

        # Update the contact
        # Update with explicit headers
        response = abook['session'].put(
            url,
            data=vcard_content,
            headers={"Content-Type": "text/vcard"}
        )
        if response.status_code not in (200, 204):
            raise Exception(f"Failed to update contact: status {response.status_code}, body: {response.text}")
            
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
        
        url = f"{abook['url'].rstrip('/')}/{contact_id}"
        
        # Delete the contact
        response = abook['session'].delete(url)
        if response.status_code not in (200, 204):
            raise Exception(f"Failed to delete contact: status {response.status_code}")
            
        flash('Contact deleted successfully')
        return redirect(url_for('contacts'))
    except Exception as e:
        logger.error(f"Error deleting contact: {str(e)}")
        flash(f"Error deleting contact: {str(e)}")
        return redirect(url_for('contacts'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_ENV') == 'development')