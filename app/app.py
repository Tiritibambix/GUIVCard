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
import time
from typing import Dict
from threading import Lock

# Cache configuration
CACHE_TTL = 300  # 5 minutes
cache_lock = Lock()

# Simple cache for vCards with TTL and thread safety
vcard_cache = {}

def clean_cache():
    """Remove expired entries from cache"""
    current_time = time.time()
    with cache_lock:
        expired = [k for k, v in vcard_cache.items()
                  if current_time - v['timestamp'] > CACHE_TTL]
        for k in expired:
            del vcard_cache[k]
            logger.debug(f"Removed expired cache entry for {k}")

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
        if ";" in data["N"]:
            # Already formatted as N:last;first;;;
            lines.append(f"N:{data['N']}")
        else:
            # Parse name into last;first
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
            "ADR:;;{street};{city};;{postal};{country}".format(
                street=str(adr.get("street", "")),
                city=str(adr.get("city", "")),
                postal=str(adr.get("postal", "")),
                country=str(adr.get("country", ""))
            )
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
                # Process form data
                vcard_data = {
                    "FN": f"{request.form.get('first_name', '').strip()} {request.form.get('last_name', '').strip()}".strip(),
                    "N": f"{request.form.get('last_name', '').strip()};{request.form.get('first_name', '').strip()};;;",
                    "EMAIL": request.form.get('email', '').strip(),
                }

                # Add optional fields
                if phone := request.form.get('phone', '').strip():
                    vcard_data["TEL"] = phone

                if org := request.form.get('organization', '').strip():
                    vcard_data["ORG"] = org

                # Store URL as-is if provided
                if contact_url := request.form.get('url', '').strip():
                    vcard_data["URL"] = contact_url

                if bday := request.form.get('birthday', '').strip():
                    # Convert DD/MM/YYYY to YYYY-MM-DD
                    if '/' in bday:
                        day, month, year = bday.split('/')
                        vcard_data["BDAY"] = f"{year}-{month}-{day}"
                    else:
                        vcard_data["BDAY"] = bday

                # Process address if any field is provided
                address_fields = {
                    'street': request.form.get('street', '').strip(),
                    'city': request.form.get('city', '').strip(),
                    'postal': request.form.get('postal', '').strip(),
                    'country': request.form.get('country', '').strip()
                }
                if any(address_fields.values()):
                    vcard_data["ADR"] = address_fields

                if note := request.form.get('note', '').strip():
                    vcard_data["NOTE"] = note

                # Process photo if uploaded
                if 'photo' in request.files:
                    photo_file = request.files['photo']
                    if photo_file and photo_file.filename:
                        photo_data = photo_file.read()
                        vcard_data["PHOTO"] = photo_data

                # Generate vCard content
                vcard_content = generate_vcard(vcard_data)
                logger.debug(f"Generated vCard:\n{vcard_content}")
                
                # Generate vCard
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
        # List contacts via PROPFIND
        contacts = []
        logger.info("Listing contacts...")
        
        response = abook['session'].request(
            'PROPFIND',
            abook['url'],
            headers={
                'Depth': '1',
                'Content-Type': 'application/xml; charset=utf-8'
            }
        )
        
        if response.status_code == 207:
            logger.info(f"Found response from address book: {abook['url']}")
            logger.info(f"Raw response content: {response.content.decode()}")
            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.content)
            logger.info("Parsed XML response")
            
            # Debug namespaces in the response
            for prefix, uri in root.nsmap.items() if hasattr(root, 'nsmap') else []:
                logger.info(f"Found namespace: {prefix} -> {uri}")
            
            # Process each response element
            ns = {
                'D': 'DAV:',
                'CARD': 'urn:ietf:params:xml:ns:carddav'
            }
            for elem in root.findall('.//D:response', ns):
                href = elem.find('.//D:href', ns).text
                if not href.endswith('.vcf'):
                    continue

                # Get ETag for future operations
                etag = elem.find('.//D:getetag', ns)
                etag = etag.text if etag is not None else None

                # Get vCard data directly from PROPFIND response
                # Clean cache before processing
                clean_cache()
                
                # Get the vCard data with caching
                card_url = urlparse(CARDDAV_URL).scheme + '://' + urlparse(CARDDAV_URL).netloc + href
                contact_id = href.split('/')[-1]
                
                with cache_lock:
                    # Check if we have a cached version
                    cached = vcard_cache.get(contact_id)
                    card_response = None
                    
                    if cached:
                        # Verify if cached version is still valid using HEAD request
                        head = abook['session'].head(card_url)
                        if head.status_code == 200:
                            current_etag = head.headers.get('ETag', '').strip('"')
                            if current_etag == cached.get('etag'):
                                logger.info(f"Using cached vCard for {contact_id}")
                                card_response = type('Response', (), {
                                    'status_code': 200,
                                    'text': cached['data'],
                                    'headers': {'ETag': current_etag}
                                })
                    
                    if card_response is None:
                        # Fetch fresh data
                        logger.info(f"Fetching vCard from: {card_url}")
                        card_response = abook['session'].get(card_url)
                        if card_response.status_code == 200:
                            etag = card_response.headers.get('ETag', '').strip('"')
                            # Cache the response
                            vcard_cache[contact_id] = {
                                'data': card_response.text,
                                'etag': etag,
                                'timestamp': time.time()
                            }
                            logger.info(f"Cached vCard for {contact_id}")
                        else:
                            logger.warning(f"Failed to fetch vCard {href}: {card_response.status_code}")
                            continue
                    
                    # Store ETag in session for updates
                    if card_response.status_code == 200:
                        etag = card_response.headers.get('ETag', '').strip('"')
                        if etag:
                            session[f'etag_{contact_id}'] = etag
                            logger.info(f"Stored ETag for {contact_id}: {etag}")

                try:
                    # Store the ETag in session for later use, using just the filename as key
                    contact_id = href.split('/')[-1]
                    if etag:
                        session[f'etag_{contact_id}'] = etag.strip('"')  # Remove quotes from ETag
                        
                    # Parse the vCard data directly from PROPFIND response
                    vobj = vobject.readOne(vcard_data.text)
                    logger.info(f"Parsed vCard: {vcard_data}")
                    
                    # If successful, extract data safely
                    contact_info = {
                        'id': contact_id,
                        'uid': getattr(vobj, 'uid', '').value if hasattr(vobj, 'uid') else '',
                        'name': getattr(vobj.fn, 'value', 'No Name'),
                        'first_name': '',
                        'last_name': '',
                        'email': '',
                        'phone': '',
                        'org': '',
                        'url': '',
                        'birthday': '',
                        'note': '',
                        'photo': None,
                        'address': None
                    }

                    # Parse name components
                    try:
                        if 'n' in vcard_data.contents:
                            contact_info['first_name'] = vcard_data.n.value.given or ''
                            contact_info['last_name'] = vcard_data.n.value.family or ''
                    except Exception:
                        logger.debug(f"Could not parse N field for contact {href}")

                    # Parse other fields
                    try:
                        if 'email' in vcard_data.contents:
                            contact_info['email'] = vcard_data.email.value
                    except Exception:
                        logger.debug(f"Could not parse email for contact {href}")

                    try:
                        if 'tel' in vcard_data.contents:
                            contact_info['phone'] = vcard_data.tel.value
                    except Exception:
                        logger.debug(f"Could not parse phone for contact {href}")

                    try:
                        if 'org' in vcard_data.contents:
                            contact_info['org'] = vcard_data.org.value[0]
                    except Exception:
                        logger.debug(f"Could not parse org for contact {href}")

                    try:
                        if 'url' in vcard_data.contents:
                            contact_info['url'] = vcard_data.url.value.strip('<>')
                    except Exception:
                        logger.debug(f"Could not parse URL for contact {href}")
                    try:
                        if 'bday' in vcard_data.contents:
                            # Convert YYYY-MM-DD to DD/MM/YYYY
                            date_str = vcard_data.bday.value
                            if '-' in date_str:
                                year, month, day = date_str.split('-')
                                contact_info['birthday'] = f"{day}/{month}/{year}"
                            else:
                                contact_info['birthday'] = date_str
                    except Exception:
                        logger.debug(f"Could not parse birthday for contact {href}")


                    try:
                        if 'note' in vcard_data.contents:
                            contact_info['note'] = vcard_data.note.value
                    except Exception:
                        logger.debug(f"Could not parse note for contact {href}")

                    # Process photo carefully
                    try:
                        if 'photo' in vcard_data.contents:
                            photo = vcard_data.photo.value
                            if isinstance(photo, bytes):
                                contact_info['photo'] = base64.b64encode(photo).decode('utf-8')
                    except Exception:
                        logger.debug(f"Could not parse photo for contact {href}")

                    # Process address carefully
                    try:
                        if 'adr' in vcard_data.contents:
                            adr = vcard_data.adr.value
                            contact_info['address'] = {
                                'street': adr.street or '',
                                'city': adr.city or '',
                                'postal': adr.code or '',
                                'country': adr.country or ''
                            }
                    except Exception:
                        logger.debug(f"Could not parse address for contact {href}")
                    
                    contacts.append(contact_info)
                    logger.debug(f"Parsed contact: {contact_info['name']} ({href})")
                    
                except Exception as e:
                    logger.warning(f"Could not parse vCard {href}: {e}")
                    continue
                    continue
        else:
            logger.error(f"Failed to list contacts: {response.status_code}")
        contacts.sort(key=lambda c: (
            (c['last_name'] or '').strip().lower(),
            (c['first_name'] or '').strip().lower()
        ))
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
        
        # Get stored ETag for this contact
        etag = session.get(f'etag_{contact_id}')
        if not etag:
            logger.warning("No ETag found for contact, proceeding without optimistic locking")
            
        # Initialize vcard_data with UID from form
        vcard_data = {
            "UID": request.form.get('uid')  # UID should be passed from the form
        }
        
        if not vcard_data["UID"]:
            raise Exception("No UID provided for contact update")
        
        # Handle photo: keep existing unless new one uploaded
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            vcard_data["PHOTO"] = photo_file.read()
        
        # Process form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        full_name = f"{first_name} {last_name}".strip()
        
        # Update other fields without overwriting vcard_data
        vcard_data.update({
            "FN": full_name,
            "N": f"{last_name};{first_name};;;",  # Correct N format: last;first;;;
            "EMAIL": request.form.get('email', '').strip(),
        })
        
        # Add optional fields
        if phone := request.form.get('phone', '').strip():
            vcard_data["TEL"] = phone
            
        if org := request.form.get('organization', '').strip():
            vcard_data["ORG"] = org
            
        if website_url := request.form.get('url', '').strip():
            vcard_data["URL"] = website_url
            
        if bday := request.form.get('birthday', '').strip():
            vcard_data["BDAY"] = bday
            
        # Process address if any field is provided
        address_fields = {
            'street': request.form.get('street', '').strip(),
            'city': request.form.get('city', '').strip(),
            'postal': request.form.get('postal', '').strip(),
            'country': request.form.get('country', '').strip()
        }
        if any(address_fields.values()):
            vcard_data["ADR"] = address_fields
            
        if note := request.form.get('note', '').strip():
            vcard_data["NOTE"] = note
            
        # Fetch existing vCard to get its UID
        existing = abook['session'].get(url)
        if existing.status_code != 200:
            raise Exception(f"Could not fetch existing vCard for UID check: {existing.status_code}")
        
        try:
            vobj = vobject.readOne(existing.text)
            vcard_data["UID"] = vobj.uid.value  # Preserve the existing UID
            logger.info(f"Reusing existing UID: {vobj.uid.value}")
        except Exception as parse_err:
            raise Exception(f"Failed to parse existing vCard for UID: {parse_err}")
            
        # Generate updated vCard content with preserved UID
        vcard_content = generate_vcard(vcard_data)
        logger.info(f"Updating vCard at {url}:\n{vcard_content}")
        
        # Update the contact
        # Prepare headers with ETag if available
        headers = {
            "Content-Type": "text/vcard",
            "If-Match": f'"{etag}"' if etag else "*"
        }
        
        response = abook['session'].put(
            url,
            data=vcard_content,
            headers=headers
        )
        if response.status_code not in (200, 201, 204):
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