from flask import Flask, request, render_template, redirect, url_for, session, flash
from functools import wraps
import os
import vobject
import logging
import sys
import requests
from urllib.parse import urlparse
import base64
import uuid
import secrets
from typing import Dict

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('guivcard')
logging.getLogger('urllib3').setLevel(logging.WARNING)

app = Flask(__name__)

secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    logger.warning("SECRET_KEY not set — generating ephemeral key. Sessions will be lost on restart.")
    secret_key = secrets.token_hex(32)
app.secret_key = secret_key

# ---------------------------------------------------------------------------
# CardDAV URL construction
# CARDDAV_URL supports {username} placeholder for multi-user setups:
#   http://radicale:5232/{username}/contacts/
# ---------------------------------------------------------------------------
CARDDAV_URL_TEMPLATE = os.environ.get('CARDDAV_URL', '').rstrip('/')
if not CARDDAV_URL_TEMPLATE:
    logger.error("CARDDAV_URL environment variable is not set.")
else:
    logger.info("GUIVCard starting. CardDAV template configured.")


def build_user_url(username: str) -> str:
    if '{username}' in CARDDAV_URL_TEMPLATE:
        return CARDDAV_URL_TEMPLATE.replace('{username}', username)
    return CARDDAV_URL_TEMPLATE


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf():
    token = request.form.get('csrf_token')
    if not token or token != session.get('csrf_token'):
        logger.warning("CSRF validation failed")
        return False
    return True


app.jinja_env.globals['csrf_token'] = generate_csrf_token


# ---------------------------------------------------------------------------
# Auth — verified against Radicale via PROPFIND
# ---------------------------------------------------------------------------

def check_auth(username: str, password: str) -> bool:
    """Authenticate by PROPFIND against the user's CardDAV collection."""
    if not username or not password:
        return False
    user_url = build_user_url(username)
    try:
        resp = requests.request(
            'PROPFIND', user_url,
            auth=(username, password),
            headers={'Depth': '0', 'User-Agent': 'GUIVCard/2.0'},
            timeout=10
        )
        # CodeQL SSRF note: user_url is derived from CARDDAV_URL_TEMPLATE (server-side env var).
        # Only the {username} fragment is user-controlled, not the host/scheme.
        # noinspection PyUnresolvedReferences
        success = resp.status_code == 207
        logger.info(f"Auth attempt for user: CardDAV returned {resp.status_code}")
        return success
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return False


def get_user_session() -> requests.Session:
    s = requests.Session()
    # Credentials are stored in the signed Flask session (not logged anywhere).
    s.auth = (session['username'], session['password'])
    s.headers.update({'User-Agent': 'GUIVCard/2.0'})
    return s


def get_user_carddav_url() -> str:
    return build_user_url(session['username'])


def check_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# vCard helpers
# ---------------------------------------------------------------------------

def escape_vcard_value(value: str) -> str:
    if not value:
        return ''
    value = value.replace('\\', '\\\\')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '')
    value = value.replace(',', '\\,')
    return value


def generate_vcard(data: Dict) -> str:
    uid = data.get('UID') or str(uuid.uuid4())
    lines = ['BEGIN:VCARD', 'VERSION:3.0']

    if fn := data.get('FN'):
        lines.append(f"FN:{escape_vcard_value(fn)}")

    if n_val := data.get('N'):
        if ';' in n_val:
            lines.append(f"N:{n_val}")
        else:
            parts = n_val.split(' ', 1)
            last = escape_vcard_value(parts[0])
            first = escape_vcard_value(parts[1]) if len(parts) > 1 else ''
            lines.append(f"N:{last};{first};;;")

    if org := data.get('ORG'):
        lines.append(f"ORG:{escape_vcard_value(org)}")
    if email := data.get('EMAIL'):
        lines.append(f"EMAIL:{escape_vcard_value(email)}")
    if tel := data.get('TEL'):
        lines.append(f"TEL:{escape_vcard_value(tel)}")

    if adr := data.get('ADR'):
        lines.append(
            "ADR:;;{street};{city};;{postal};{country}".format(
                street=escape_vcard_value(str(adr.get('street', ''))),
                city=escape_vcard_value(str(adr.get('city', ''))),
                postal=escape_vcard_value(str(adr.get('postal', ''))),
                country=escape_vcard_value(str(adr.get('country', '')))
            )
        )

    if url := data.get('URL'):
        lines.append(f"URL:{escape_vcard_value(url)}")

    if photo := data.get('PHOTO'):
        if isinstance(photo, bytes):
            photo_b64 = base64.b64encode(photo).decode('utf-8')
            lines.append(f"PHOTO;ENCODING=b;TYPE=JPEG:{photo_b64}")

    if bday := data.get('BDAY'):
        lines.append(f"BDAY:{escape_vcard_value(bday)}")

    if note := data.get('NOTE'):
        lines.append(f"NOTE:{escape_vcard_value(note)}")

    lines.append(f"UID:{uid}")
    lines.append('END:VCARD')
    lines.append('')
    return '\r\n'.join(lines)


def normalize_birthday_to_iso(bday: str) -> str:
    bday = bday.strip()
    if '/' in bday:
        parts = bday.split('/')
        if len(parts) == 3:
            day, month, year = parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return bday


def normalize_birthday_to_display(bday: str) -> str:
    bday = bday.strip()
    if '-' in bday:
        parts = bday.split('-')
        if len(parts) == 3:
            year, month, day = parts
            return f"{day}/{month}/{year}"
    return bday


def parse_contacts_from_report(response_content: bytes) -> list:
    from xml.etree import ElementTree
    contacts = []

    try:
        root = ElementTree.fromstring(response_content)
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse REPORT XML: {e}")
        return contacts

    ns = {'D': 'DAV:', 'C': 'urn:ietf:params:xml:ns:carddav'}

    for elem in root.findall('.//D:response', ns):
        href_el = elem.find('.//D:href', ns)
        if href_el is None:
            continue
        href = href_el.text or ''
        if not href.endswith('.vcf'):
            continue

        address_data = elem.find('.//C:address-data', ns)
        if address_data is None or not address_data.text:
            logger.debug(f"No address-data for {href}")
            continue

        try:
            vcard_data = vobject.readOne(address_data.text)
        except Exception as e:
            logger.warning(f"Could not parse vCard {href}: {e}")
            continue

        fn_val = ''
        try:
            fn_val = vcard_data.fn.value
        except Exception:
            pass

        contact = {
            'id': href.split('/')[-1],
            'name': fn_val or 'No Name',
            'first_name': '', 'last_name': '',
            'email': '', 'phone': '', 'org': '',
            'url': '', 'birthday': '', 'note': '',
            'photo': None, 'address': None
        }

        try:
            if 'n' in vcard_data.contents:
                contact['first_name'] = vcard_data.n.value.given or ''
                contact['last_name'] = vcard_data.n.value.family or ''
        except Exception:
            pass

        try:
            if 'email' in vcard_data.contents:
                contact['email'] = vcard_data.email.value
        except Exception:
            pass

        try:
            if 'tel' in vcard_data.contents:
                contact['phone'] = vcard_data.tel.value
        except Exception:
            pass

        try:
            if 'org' in vcard_data.contents:
                val = vcard_data.org.value
                contact['org'] = val[0] if isinstance(val, list) else val
        except Exception:
            pass

        try:
            if 'url' in vcard_data.contents:
                contact['url'] = vcard_data.url.value.strip('<>')
        except Exception:
            pass

        try:
            if 'bday' in vcard_data.contents:
                contact['birthday'] = normalize_birthday_to_display(vcard_data.bday.value)
        except Exception:
            pass

        try:
            if 'note' in vcard_data.contents:
                contact['note'] = vcard_data.note.value
        except Exception:
            pass

        try:
            if 'photo' in vcard_data.contents:
                photo = vcard_data.photo.value
                if isinstance(photo, bytes):
                    contact['photo'] = base64.b64encode(photo).decode('utf-8')
        except Exception:
            pass

        try:
            if 'adr' in vcard_data.contents:
                adr = vcard_data.adr.value
                contact['address'] = {
                    'street': adr.street or '',
                    'city': adr.city or '',
                    'postal': adr.code or '',
                    'country': adr.country or ''
                }
        except Exception:
            pass

        contacts.append(contact)
        logger.debug(f"Parsed contact: {contact['name']} ({href})")

    return contacts


def sort_contacts(contacts: list, sort_by: str = 'first_name') -> list:
    """Sort contacts by the given key. Default: first_name then last_name."""
    if sort_by == 'last_name':
        key = lambda c: (
            (c['last_name'] or c['name']).strip().lower(),
            (c['first_name'] or '').strip().lower()
        )
    elif sort_by == 'org':
        key = lambda c: (
            (c['org'] or '').strip().lower(),
            (c['first_name'] or c['name']).strip().lower()
        )
    elif sort_by == 'email':
        key = lambda c: (c['email'] or '').strip().lower()
    else:  # first_name (default)
        key = lambda c: (
            (c['first_name'] or c['name']).strip().lower(),
            (c['last_name'] or '').strip().lower()
        )
    try:
        return sorted(contacts, key=key)
    except Exception as e:
        logger.error(f"Sort error: {e}")
        return contacts


def collect_vcard_data_from_form(form, files=None) -> dict:
    first_name = form.get('first_name', '').strip()
    last_name = form.get('last_name', '').strip()
    full_name = f"{first_name} {last_name}".strip()

    data = {
        'FN': full_name,
        'N': f"{last_name};{first_name};;;",
        'EMAIL': form.get('email', '').strip(),
    }

    if phone := form.get('phone', '').strip():
        data['TEL'] = phone
    if org := form.get('organization', '').strip():
        data['ORG'] = org
    if url := form.get('url', '').strip():
        data['URL'] = url
    if bday := form.get('birthday', '').strip():
        data['BDAY'] = normalize_birthday_to_iso(bday)
    if note := form.get('note', '').strip():
        data['NOTE'] = note

    address_fields = {
        'street': form.get('street', '').strip(),
        'city': form.get('city', '').strip(),
        'postal': form.get('postal', '').strip(),
        'country': form.get('country', '').strip()
    }
    if any(address_fields.values()):
        data['ADR'] = address_fields

    if files and 'photo' in files:
        photo_file = files['photo']
        if photo_file and photo_file.filename:
            data['PHOTO'] = photo_file.read()

    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('contacts'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('contacts'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter a username and password.', 'error')
            return render_template('login.html')

        if check_auth(username, password):
            session['username'] = username
            session['password'] = password
            logger.info("User logged in successfully.")
            return redirect(url_for('contacts'))

        logger.warning("Failed login attempt.")
        flash('Invalid credentials or access denied by the CardDAV server.', 'error')
        return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    logger.info("User logged out.")
    return redirect(url_for('login'))


@app.route('/health')
@check_login_required
def health_check():
    carddav_url = get_user_carddav_url()
    s = get_user_session()
    status = {'carddav_url': carddav_url, 'is_healthy': False, 'status_code': None, 'error': None}
    try:
        resp = s.request('PROPFIND', carddav_url, headers={'Depth': '1'}, timeout=10)
        status['is_healthy'] = resp.status_code == 207
        status['status_code'] = resp.status_code
        status['message'] = (
            'Successfully connected to address book.'
            if status['is_healthy']
            else f"Unexpected server response: {resp.status_code}"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        status['error'] = str(e)
        status['message'] = 'Could not reach the CardDAV server.'
    return render_template('health.html', status=status)


@app.route('/contacts', methods=['GET', 'POST'])
@check_login_required
def contacts():
    s = get_user_session()
    carddav_url = get_user_carddav_url()

    if request.method == 'POST':
        if not validate_csrf():
            flash('Invalid request (CSRF).', 'error')
            return redirect(url_for('contacts'))
        try:
            vcard_data = collect_vcard_data_from_form(request.form, request.files)
            vcard_content = generate_vcard(vcard_data)
            filename = f"{base64.urlsafe_b64encode(os.urandom(12)).decode()}.vcf"
            put_url = f"{carddav_url.rstrip('/')}/{filename}"
            resp = s.put(put_url, data=vcard_content, headers={'Content-Type': 'text/vcard'}, timeout=10)
            if resp.status_code not in (201, 204):
                raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")
            flash('Contact created successfully.', 'success')
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            flash(f"Error creating contact: {e}", 'error')
        return redirect(url_for('contacts'))

    # Sort preference from query string (persisted in session)
    sort_by = request.args.get('sort', session.get('sort_by', 'first_name'))
    session['sort_by'] = sort_by

    contact_list = []
    try:
        report_body = '''<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
    <D:prop>
        <D:getetag/>
        <C:address-data/>
    </D:prop>
</C:addressbook-query>'''

        resp = s.request(
            'REPORT', carddav_url,
            headers={
                'Depth': '1',
                'Content-Type': 'application/xml; charset=utf-8',
            },
            data=report_body.encode('utf-8'),
            timeout=30
        )

        logger.info(f"REPORT → {resp.status_code}")

        if resp.status_code == 207:
            contact_list = parse_contacts_from_report(resp.content)
            contact_list = sort_contacts(contact_list, sort_by)
            logger.info(f"Loaded {len(contact_list)} contacts.")
        else:
            logger.error(f"REPORT failed: {resp.status_code} — {resp.text[:300]}")
            flash(f"Could not load contacts (status {resp.status_code}).", 'error')
    except Exception as e:
        logger.error(f"Error listing contacts: {e}")
        flash(f"Error: {e}", 'error')

    return render_template('index.html', contacts=contact_list, sort_by=sort_by)


@app.route('/contacts/update', methods=['POST'])
@check_login_required
def update_contact():
    if not validate_csrf():
        flash('Invalid request (CSRF).', 'error')
        return redirect(url_for('contacts'))

    s = get_user_session()
    carddav_url = get_user_carddav_url()

    try:
        contact_id = request.form.get('contact_id', '').strip()
        if not contact_id:
            raise Exception("Missing contact_id")

        contact_url = f"{carddav_url.rstrip('/')}/{contact_id}"

        existing_resp = s.get(contact_url, timeout=10)
        if existing_resp.status_code != 200:
            raise Exception(f"Could not fetch contact: status {existing_resp.status_code}")

        try:
            vobj = vobject.readOne(existing_resp.text)
            existing_uid = vobj.uid.value if 'uid' in vobj.contents else str(uuid.uuid4())
        except Exception as parse_err:
            raise Exception(f"Could not parse existing vCard: {parse_err}")

        vcard_data = collect_vcard_data_from_form(request.form, request.files)
        vcard_data['UID'] = existing_uid

        if 'PHOTO' not in vcard_data and 'photo' in vobj.contents:
            vcard_data['PHOTO'] = vobj.photo.value

        vcard_content = generate_vcard(vcard_data)
        resp = s.put(contact_url, data=vcard_content, headers={'Content-Type': 'text/vcard'}, timeout=10)
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")

        flash('Contact updated successfully.', 'success')
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        flash(f"Error updating contact: {e}", 'error')

    return redirect(url_for('contacts'))


@app.route('/contacts/<contact_id>/delete', methods=['POST'])
@check_login_required
def delete_contact(contact_id):
    if not validate_csrf():
        flash('Invalid request (CSRF).', 'error')
        return redirect(url_for('contacts'))

    s = get_user_session()
    carddav_url = get_user_carddav_url()

    try:
        contact_url = f"{carddav_url.rstrip('/')}/{contact_id}"
        resp = s.delete(contact_url, timeout=10)
        if resp.status_code not in (200, 204):
            raise Exception(f"Status {resp.status_code}")
        flash('Contact deleted.', 'success')
    except Exception as e:
        logger.error(f"Error deleting contact: {e}")
        flash(f"Error deleting contact: {e}", 'error')

    return redirect(url_for('contacts'))


if __name__ == '__main__':
    # Development only — production runs via gunicorn (see Dockerfile)
    app.run(host='0.0.0.0', port=5000, debug=False)
