from flask import Flask, request, render_template, redirect, url_for, session, flash, g, Response
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
import threading
import time
import io
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageOps

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

# The cookie carries an opaque session id and nothing else — the CardDAV
# password stays in this process (see SessionStore below).
# SECURE_COOKIES is off by default because the documented quick start serves
# plain HTTP on a LAN; turn it on when running behind an HTTPS reverse proxy.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=os.environ.get('SECURE_COOKIES', '').strip().lower() in ('1', 'true', 'yes'),
    # An unbounded POST body would be read into memory; with several threads
    # serving uploads, that is enough to exhaust the container. Photos are
    # scaled down well below this, so the limit only stops abuse.
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)
if app.config['SESSION_COOKIE_SECURE']:
    logger.info("SECURE_COOKIES enabled — the session cookie requires HTTPS.")

# How long to wait for the CardDAV server. A cold server, or a large address
# book on modest hardware, takes well over the 10 seconds this used to allow.
CARDDAV_TIMEOUT = 60

# The app loads nothing from anywhere else: no CDN, no external script, no
# frame. Photos render from data: URLs. Fonts come from Google Fonts, which is
# the one exception, so the stylesheet and font origins are named explicitly.
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
}


@app.errorhandler(413)
def payload_too_large(_error):
    """MAX_CONTENT_LENGTH rejected the upload before it was read."""
    limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    flash(f"That file is too large. The limit is {limit_mb} MB.", 'error')
    return redirect(url_for('contacts') if is_signed_in() else url_for('login'))


@app.before_request
def generate_csp_nonce():
    """A fresh nonce per response, for the templates' one <script> block.

    This is what lets script-src drop 'unsafe-inline': an injected script
    cannot carry a nonce it has no way to read. The templates also carry no
    inline event handler, which a nonce would not cover.
    """
    g.csp_nonce = secrets.token_urlsafe(16)


@app.context_processor
def inject_csp_nonce():
    return {'csp_nonce': g.get('csp_nonce', '')}


@app.after_request
def set_security_headers(response):
    nonce = g.get('csp_nonce', '')
    # style-src keeps 'unsafe-inline' for the inline <style> block, which
    # cannot inject script; script-src does not.
    response.headers.setdefault('Content-Security-Policy', (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ))
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # HSTS only means anything over HTTPS, and pinning it on a plain-HTTP LAN
    # deployment would be a promise the server cannot keep.
    if app.config['SESSION_COOKIE_SECURE']:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000')
    return response

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


# Parse the server-side template once at startup into fixed, trusted components.
# scheme, netloc, and the path template are all derived from the env var only —
# never from user input.
_TEMPLATE_PARSED  = urlparse(CARDDAV_URL_TEMPLATE)
_FIXED_SCHEME     = _TEMPLATE_PARSED.scheme    # e.g. "https"
_FIXED_NETLOC     = _TEMPLATE_PARSED.netloc    # e.g. "radicale:5232"
_FIXED_PATH_TMPL  = _TEMPLATE_PARSED.path      # e.g. "/{username}/contacts/"
_FIXED_QUERY      = _TEMPLATE_PARSED.query
_FIXED_FRAGMENT   = _TEMPLATE_PARSED.fragment


def _sanitize_username(username: str) -> str:
    """
    Strip any character that could alter URL structure.
    Only alphanumeric, hyphen, underscore and dot are allowed in a Radicale username.
    Raises ValueError for invalid usernames.
    """
    if not re.match(r'^[A-Za-z0-9._-]+$', username):
        raise ValueError("Username contains invalid characters.")
    return username


def build_user_url(username: str) -> str:
    """
    Assemble the CardDAV URL from purely server-side components.
    scheme, netloc and path structure come from CARDDAV_URL_TEMPLATE (env var).
    username is sanitized to [A-Za-z0-9._-] before being inserted into the path.
    CodeQL taint: username only reaches the path segment, never scheme or netloc.
    """
    safe_username = _sanitize_username(username)  # raises ValueError if invalid

    if '{username}' in _FIXED_PATH_TMPL:
        path = _FIXED_PATH_TMPL.replace('{username}', safe_username)
    else:
        path = _FIXED_PATH_TMPL

    # Re-assemble from fixed server-side parts — user input only in `path`.
    from urllib.parse import urlunparse
    return urlunparse((_FIXED_SCHEME, _FIXED_NETLOC, path, '', _FIXED_QUERY, _FIXED_FRAGMENT))


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
# Server-side session store
#
# The CardDAV password never leaves this process. The browser holds only an
# opaque session id in a signed, HttpOnly cookie, so a stolen or inspected
# cookie yields no reusable credential.
#
# Sessions live in memory: they are dropped on restart, and the app must run
# in a single worker process (see the gunicorn flags in the Dockerfile).
# ---------------------------------------------------------------------------

SESSION_IDLE_TIMEOUT = 12 * 3600      # no request for 12 hours ends a session
SESSION_ABSOLUTE_MAX = 7 * 24 * 3600  # 7 days maximum, however active
MAX_SESSIONS_PER_USER = 20
MAX_SESSIONS_TOTAL = 10000


class SessionStore:
    """Thread-safe in-memory session store. Credentials are never logged."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, dict] = {}

    @staticmethod
    def _is_expired(rec: dict, now: float) -> bool:
        return (now - rec['last_seen'] > SESSION_IDLE_TIMEOUT
                or now - rec['created'] > SESSION_ABSOLUTE_MAX)

    def _sweep(self, now: float) -> None:
        """Drop expired sessions. The caller must hold the lock."""
        for sid in [s for s, r in self._sessions.items() if self._is_expired(r, now)]:
            del self._sessions[sid]

    def create(self, username: str, password: str) -> Optional[str]:
        """Open a session and return its id, or None if the store is full."""
        now = time.time()
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._sweep(now)
            if len(self._sessions) >= MAX_SESSIONS_TOTAL:
                logger.error("Session store full — refusing a new session.")
                return None
            # Past the per-account cap, the oldest sessions of that account go.
            owned = sorted(
                (r['created'], s) for s, r in self._sessions.items()
                if r['username'] == username
            )
            for _, old_sid in owned[:max(0, len(owned) - MAX_SESSIONS_PER_USER + 1)]:
                del self._sessions[old_sid]
            self._sessions[sid] = {
                'username': username,
                'password': password,
                'created': now,
                'last_seen': now,
            }
        return sid

    def get(self, sid: str) -> Optional[dict]:
        """Return the session's credentials and mark it used, or None."""
        if not sid:
            return None
        now = time.time()
        with self._lock:
            rec = self._sessions.get(sid)
            if rec is None:
                return None
            if self._is_expired(rec, now):
                del self._sessions[sid]
                return None
            rec['last_seen'] = now
            return {'username': rec['username'], 'password': rec['password']}

    def destroy(self, sid: str) -> None:
        if not sid:
            return
        with self._lock:
            self._sessions.pop(sid, None)


SESSIONS = SessionStore()


# ---------------------------------------------------------------------------
# Auth — verified against Radicale via PROPFIND
# ---------------------------------------------------------------------------

def check_auth(username: str, password: str) -> bool:
    """Authenticate by PROPFIND against the user's CardDAV collection.
    build_user_url() sanitizes username to [A-Za-z0-9._-] and assembles the URL
    from server-side-only components, cutting the CodeQL taint path.
    """
    if not username or not password:
        return False
    try:
        user_url = build_user_url(username)
    except ValueError as e:
        logger.error(f"Auth rejected — invalid username format: {e}")
        return False
    try:
        resp = requests.request(
            'PROPFIND', user_url,
            auth=(username, password),
            headers={'Depth': '0', 'User-Agent': 'GUIVCard/2.0'},
            timeout=CARDDAV_TIMEOUT
        )
        success = resp.status_code == 207
        logger.info(f"Auth attempt: CardDAV returned {resp.status_code}")
        return success
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return False


def get_user_session() -> requests.Session:
    s = requests.Session()
    # Credentials come from the in-process store, never from the cookie.
    s.auth = (g.username, g.password)
    s.headers.update({'User-Agent': 'GUIVCard/2.0'})
    return s


def get_user_carddav_url() -> str:
    return build_user_url(g.username)


def is_signed_in() -> bool:
    return SESSIONS.get(session.get('sid', '')) is not None


def check_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        rec = SESSIONS.get(session.get('sid', ''))
        if rec is None:
            session.clear()
            return redirect(url_for('login'))
        g.username = rec['username']
        g.password = rec['password']
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_current_user():
    """Templates read `current_user`; the cookie no longer carries the name."""
    return {'current_user': g.get('username')}


# ---------------------------------------------------------------------------
# vCard helpers
# ---------------------------------------------------------------------------

# Writes go through vobject rather than string concatenation, for two reasons.
#
# It escapes values per RFC 6350 — the semicolon included, which hand-rolled
# escaping missed, so an organization or note containing one no longer breaks
# the field structure.
#
# More importantly, an edit now applies the form's fields *onto the card the
# server returned*, instead of rebuilding a card from the handful of fields the
# editor shows. Everything else survives: additional e-mails and phone numbers,
# TYPE parameters (home/work/cell), CATEGORIES and group memberships, NICKNAME,
# TITLE, ROLE, IMPP, custom X-* properties — all of it used to be destroyed the
# first time a contact was saved from this UI.

IMAGE_SIGNATURES = (
    (b'\xff\xd8\xff', 'JPEG', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'PNG', 'image/png'),
    (b'GIF87a', 'GIF', 'image/gif'),
    (b'GIF89a', 'GIF', 'image/gif'),
)


def detect_image(data: bytes) -> Optional[Tuple[str, str]]:
    """Return (vCard TYPE, MIME type) for a supported image, else None.

    Read from the bytes themselves: an uploaded PNG used to be labelled
    TYPE=JPEG and served as image/jpeg regardless of what it actually was.
    """
    if not data:
        return None
    for signature, vcard_type, mime in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return vcard_type, mime
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'WEBP', 'image/webp'
    return None


# A photo is bounded on both axes: 1024 px is past what any client displays
# (Android keeps 720), and half a megabyte keeps the card under the size a
# stock server accepts — an nginx in front of a CardDAV server commonly stops
# at 1 MB, and base64 inflates the bytes by a third.
PHOTO_MAX_DIMENSION = 1024
PHOTO_MAX_BYTES = 512 * 1024

# Decoding is bounded too: an 8 MB PNG can expand into gigabytes of bitmap.
# Pillow warns at this count and refuses at twice it; 40 MP is past any phone.
Image.MAX_IMAGE_PIXELS = 40_000_000


def normalize_photo(data: bytes) -> Tuple[bytes, str, str]:
    """Straighten, shrink and strip an uploaded photo.

    Returns (bytes, vCard TYPE, MIME type).

    An uploaded photo carries EXIF: the GPS coordinates of where it was taken,
    the camera model, the timestamp, sometimes XMP. All of that used to be
    written into the contact card and synced to every device and the server.
    Decoding and re-encoding here drops it, because nothing is carried over.

    It also applies the EXIF orientation, which Google Contacts ignores — a
    photo taken in portrait showed up lying on its side — and bounds the
    result, since a phone photo becomes several megabytes of base64 that a
    stock server refuses and every client re-downloads on each sync.
    """
    try:
        with Image.open(io.BytesIO(data)) as opened:
            # Apply the orientation flag, then drop it with everything else.
            image = ImageOps.exif_transpose(opened)
            # A palette image may carry transparency; expand it to find out.
            if image.mode == 'P':
                image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
            keeps_alpha = image.mode in ('RGBA', 'LA')
            image = image.convert('RGBA' if keeps_alpha else 'RGB')
            image.load()
            # The JPEG encoder writes only what save() is given, but the PNG
            # one falls back to im.info, so a transparent photo could carry
            # its EXIF through. Drop it here rather than rely on the encoder.
            for key in ('exif', 'xmp', 'XML:com.adobe.xmp', 'icc_profile', 'photoshop'):
                image.info.pop(key, None)
    except Exception as e:
        logger.warning(f"Could not decode uploaded photo: {type(e).__name__}")
        raise ValueError(
            "That image could not be read. Use a JPEG, PNG, GIF or WebP file."
        )

    # Transparency needs PNG; anything else is smaller as JPEG.
    fmt, vcard_type, mime = ('PNG', 'PNG', 'image/png') if keeps_alpha else ('JPEG', 'JPEG', 'image/jpeg')

    smallest = None
    for dimension in (PHOTO_MAX_DIMENSION, 800, 640, 512, 400):
        candidate = image.copy()
        candidate.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
        qualities = (90, 80, 70) if fmt == 'JPEG' else (None,)
        for quality in qualities:
            buf = io.BytesIO()
            if quality is None:
                candidate.save(buf, format=fmt, optimize=True)
            else:
                candidate.save(buf, format=fmt, quality=quality, optimize=True)
            encoded = buf.getvalue()
            if len(encoded) <= PHOTO_MAX_BYTES:
                return encoded, vcard_type, mime
            if smallest is None or len(encoded) < len(smallest):
                smallest = encoded

    # Nothing fitted the budget. The smallest attempt still beats the original,
    # and the server's own limit will report it if it is still too large.
    logger.warning(f"Photo still {len(smallest)} bytes after scaling down.")
    return smallest, vcard_type, mime


def _first(vobj, name: str):
    """The first instance of a property, or None."""
    lines = vobj.contents.get(name)
    return lines[0] if lines else None


def _set_text(vobj, name: str, value: str) -> None:
    """Set the first instance of a text property; an empty value removes it.

    Only the first instance is touched. The editor shows one e-mail address and
    one phone number, so a card holding several keeps the rest.
    """
    line = _first(vobj, name)
    if value:
        if line is None:
            line = vobj.add(name)
        line.value = value
    elif line is not None:
        vobj.remove(line)


# The TYPE tokens the editor's dropdowns own. Any other token on a property —
# INTERNET, PREF, VOICE, and whatever a client invented — is left alone, so
# choosing "Work" in the UI does not quietly drop TYPE=PREF.
MANAGED_EMAIL_TYPES = ('HOME', 'WORK', 'OTHER')
MANAGED_TEL_TYPES = ('CELL', 'HOME', 'WORK', 'FAX', 'PAGER', 'OTHER')


def read_type(line, managed: Tuple[str, ...]) -> str:
    """The first TYPE token the editor manages, or '' if the line has none."""
    for token in line.params.get('TYPE', []):
        if token.upper() in managed:
            return token.upper()
    return ''


def write_type(line, chosen: str, managed: Tuple[str, ...]) -> None:
    """Replace the managed TYPE token, keeping every other one."""
    kept = [t for t in line.params.get('TYPE', []) if t.upper() not in managed]
    tokens = kept + ([chosen] if chosen else [])
    if tokens:
        line.params['TYPE'] = tokens
    else:
        line.params.pop('TYPE', None)


def _set_typed_list(vobj, name: str, entries: List[dict], managed: Tuple[str, ...]) -> None:
    """Apply a list of {value, type} onto a multi-valued property.

    Existing lines are reused in order rather than recreated, so parameters
    the editor does not manage stay on the line they belong to. Lines past the
    end of the submitted list are removed, which is how a deleted row works.
    """
    kept = [e for e in entries if e.get('value')]
    existing = list(vobj.contents.get(name, []))

    for index, entry in enumerate(kept):
        if index < len(existing):
            line = existing[index]
        else:
            line = vobj.add(name)
        line.value = entry['value']
        write_type(line, entry.get('type', ''), managed)

    for line in existing[len(kept):]:
        vobj.remove(line)


def apply_contact_fields(vobj, data: Dict) -> None:
    """Apply the editor's fields onto a parsed card, in place.

    Any property the editor does not own is left exactly as it was parsed.
    """
    fn = data.get('FN', '').strip()
    if not fn:
        raise ValueError("A first name is required.")
    _set_text(vobj, 'fn', fn)

    # N: only the family and given components are edited, so a prefix, suffix
    # or middle name already on the card is kept.
    name_line = _first(vobj, 'n')
    if name_line is None:
        name_line = vobj.add('n')
    if not isinstance(name_line.value, vobject.vcard.Name):
        name_line.value = vobject.vcard.Name()
        name_line.isNative = True
    name_line.value.family = data.get('LAST_NAME', '')
    name_line.value.given = data.get('FIRST_NAME', '')

    # ORG is a list of organization and sub-unit components; only the first is
    # editable, so any sub-unit survives.
    org = data.get('ORG', '')
    org_line = _first(vobj, 'org')
    if org:
        if org_line is None:
            org_line = vobj.add('org')
        if isinstance(org_line.value, list) and org_line.value:
            org_line.value[0] = org
        else:
            org_line.value = [org]
            org_line.isNative = True
    elif org_line is not None:
        vobj.remove(org_line)

    _set_typed_list(vobj, 'email', data.get('EMAILS', []), MANAGED_EMAIL_TYPES)
    _set_typed_list(vobj, 'tel', data.get('TELS', []), MANAGED_TEL_TYPES)
    _set_text(vobj, 'url', data.get('URL', ''))
    # A year-less birthday keeps the form the card already used, so a card
    # written by an Apple device stays readable to Apple devices. _set_text
    # assigns to the existing line, which carries X-APPLE-OMIT-YEAR along.
    bday = data.get('BDAY', '')
    bday_line = _first(vobj, 'bday')
    if bday_line is not None:
        was_apple = (
            'X-APPLE-OMIT-YEAR' in bday_line.params
            or str(bday_line.value).strip().startswith(APPLE_OMIT_YEAR)
        )
        if bday.startswith('--') and was_apple:
            bday = f"{APPLE_OMIT_YEAR}-{bday[2:4]}-{bday[4:6]}"
        elif not bday.startswith('--'):
            # The user supplied a real year; the marker no longer applies.
            bday_line.params.pop('X-APPLE-OMIT-YEAR', None)
    _set_text(vobj, 'bday', bday)

    _set_text(vobj, 'note', data.get('NOTE', ''))

    # ADR: the form edits four of the seven components. The post box, extended
    # address and region stay as they were.
    adr = data.get('ADR') or {}
    adr_line = _first(vobj, 'adr')
    if any(adr.values()):
        if adr_line is None:
            adr_line = vobj.add('adr')
        if not isinstance(adr_line.value, vobject.vcard.Address):
            adr_line.value = vobject.vcard.Address()
            adr_line.isNative = True
        adr_line.value.street = adr.get('street', '')
        adr_line.value.city = adr.get('city', '')
        adr_line.value.code = adr.get('postal', '')
        adr_line.value.country = adr.get('country', '')
    elif adr_line is not None:
        vobj.remove(adr_line)

    # PHOTO is replaced only when a new file was uploaded, so an existing photo
    # is never re-encoded or dropped by an edit that did not concern it.
    photo = data.get('PHOTO')
    if isinstance(photo, bytes) and photo:
        normalized, vcard_type, _mime = normalize_photo(photo)
        photo_line = _first(vobj, 'photo')
        if photo_line is None:
            photo_line = vobj.add('photo')
        photo_line.value = normalized
        photo_line.encoding_param = 'B'
        photo_line.type_param = vcard_type
        photo_line.encoded = False
    elif data.get('REMOVE_PHOTO'):
        photo_line = _first(vobj, 'photo')
        if photo_line is not None:
            vobj.remove(photo_line)

    # RFC 6350 §6.7.4: REV marks the card's last change, so other clients can
    # tell this version is the newer one.
    _set_text(vobj, 'rev', datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))


def build_new_vcard(data: Dict) -> str:
    """Serialise a brand-new card."""
    vobj = vobject.vCard()
    if 'version' not in vobj.contents:
        vobj.add('version').value = '3.0'
    vobj.add('uid').value = data.get('UID') or str(uuid.uuid4())
    apply_contact_fields(vobj, data)
    return vobj.serialize(validate=False)


def serialize_updated_vcard(vobj, data: Dict) -> str:
    """Apply the form onto a parsed card and serialise it.

    validate=False: the card came from the server, and is written back as
    faithfully as we can. A cardinality quirk in someone else's card is not
    ours to reject — refusing it would be the data loss we are preventing.
    """
    apply_contact_fields(vobj, data)
    return vobj.serialize(validate=False)


# Apple stores a birthday whose year is unknown as the year 1604, marked with
# X-APPLE-OMIT-YEAR. Some iOS-written cards use 1604 without the marker.
APPLE_OMIT_YEAR = '1604'


def normalize_birthday_to_iso(bday: str) -> str:
    """`dd/mm/yyyy`, or `dd/mm` for a birthday whose year is not known.

    A year-less birthday is stored as vCard's own `--MMDD`; a card that already
    used Apple's form keeps it (see apply_contact_fields).
    """
    bday = bday.strip()
    if '/' not in bday:
        return bday
    parts = [p.strip() for p in bday.split('/')]
    if len(parts) == 2 and all(parts):
        day, month = parts
        return f"--{month.zfill(2)}{day.zfill(2)}"
    if len(parts) == 3 and all(parts):
        day, month, year = parts
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return bday


def normalize_birthday_to_display(bday: str, omit_year: bool = False) -> str:
    """The stored birthday as `dd/mm/yyyy`, or `dd/mm` when it carries no year.

    `--MMDD` used to come out as the string "0517//", and Apple's 1604 as
    "17/05/1604".
    """
    bday = (bday or '').strip()
    if not bday:
        return ''

    without_year = re.fullmatch(r'--(\d{2})-?(\d{2})', bday)
    if without_year:
        month, day = without_year.groups()
        return f"{day}/{month}"

    full = re.fullmatch(r'(\d{4})-?(\d{2})-?(\d{2})', bday)
    if full:
        year, month, day = full.groups()
        if omit_year or year == APPLE_OMIT_YEAR:
            return f"{day}/{month}"
        return f"{day}/{month}/{year}"

    # Anything else (a datetime, a partial date) is shown as stored rather
    # than mangled.
    return bday


# Properties the detail view renders in a place of their own, so they must not
# be repeated under "other fields". REV is bookkeeping, and X-APPLE-OMIT-YEAR
# modifies BDAY rather than being a field in its own right.
DETAIL_SHOWN_PROPERTIES = frozenset({
    'version', 'prodid', 'uid', 'fn', 'n', 'org', 'email', 'tel', 'adr',
    'url', 'bday', 'note', 'rev', 'x-apple-omit-year',
})

# Payloads that a list of text cannot usefully show.
DETAIL_BINARY_PROPERTIES = frozenset({'photo', 'logo', 'sound', 'key'})

# Readable names for what a card commonly carries beyond the fields the editor
# manages. Anything missing here is shown under its own upper-case name, so an
# X-* extension stays recognisable instead of being renamed or hidden.
DETAIL_LABELS = {
    'nickname': 'Nickname',
    'title': 'Job title',
    'role': 'Role',
    'impp': 'Instant messaging',
    'categories': 'Categories',
    'geo': 'Coordinates',
    'tz': 'Time zone',
    'lang': 'Language',
    'anniversary': 'Anniversary',
    'related': 'Related',
    'member': 'Group member',
    'source': 'Source',
    'kind': 'Kind',
    'gender': 'Gender',
    'x-phonetic-first-name': 'Phonetic first name',
    'x-phonetic-last-name': 'Phonetic last name',
}

# The TYPE tokens shown beside an address. The editor does not manage them, so
# this list only decides which one is worth labelling in the detail view.
ADR_DISPLAY_TYPES = ('HOME', 'WORK', 'OTHER')

# Any synced device can write these values, so they are bounded before being
# embedded in the page.
EXTRA_VALUE_MAX = 300
EXTRA_MAX_ENTRIES = 40


def _flatten_value(value) -> str:
    """One readable line for a property value, structured or not.

    Unlike _as_str, which keeps only the first element of a list, this joins
    them: a component holding several values is shown in full rather than
    silently truncated to its first.
    """
    if isinstance(value, (list, tuple)):
        return ', '.join(text for text in (_flatten_value(v) for v in value) if text)
    return _as_str(value).strip()


def card_extra_fields(vobj) -> List[dict]:
    """Everything on a card that the detail view does not show elsewhere.

    The editor cannot write these, but a save keeps every one of them. Showing
    them is the only way a person can tell they are still there.
    """
    extra: List[dict] = []

    def add(label: str, value: str) -> None:
        text = value.strip()
        if not text or len(extra) >= EXTRA_MAX_ENTRIES:
            return
        if len(text) > EXTRA_VALUE_MAX:
            text = text[:EXTRA_VALUE_MAX].rstrip() + '…'
        extra.append({'label': label, 'value': text})

    # Components of N and ORG that the editor does not expose. They belong to a
    # structured value, so they never show up as properties of their own.
    try:
        name_line = _first(vobj, 'n')
        if name_line is not None:
            for attr, label in (('prefix', 'Name prefix'),
                                ('additional', 'Middle name'),
                                ('suffix', 'Name suffix')):
                add(label, _flatten_value(getattr(name_line.value, attr, '')))
    except Exception:
        pass

    try:
        org = _first(vobj, 'org')
        if org is not None:
            units = org.value if isinstance(org.value, list) else [org.value]
            if units and isinstance(units[0], list):
                units = units[0]
            for unit in units[1:]:
                add('Organisation unit', _flatten_value(unit))
    except Exception:
        pass

    for name, lines in sorted(vobj.contents.items()):
        if name in DETAIL_SHOWN_PROPERTIES or name in DETAIL_BINARY_PROPERTIES:
            continue
        label = DETAIL_LABELS.get(name, name.upper())
        for line in lines:
            try:
                add(label, _flatten_value(line.value))
            except Exception:
                continue

    return extra


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

        # The ETag is the version the user is about to edit. It travels through
        # the page into If-Match on the write, so a change made meanwhile on
        # another device is refused rather than overwritten.
        etag_el = elem.find('.//D:getetag', ns)
        etag = (etag_el.text or '').strip() if etag_el is not None else ''

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
            'etag': etag,
            'name': fn_val or 'No Name',
            'first_name': '', 'last_name': '',
            'email': '', 'phone': '', 'org': '',
            'emails': [], 'phones': [],
            'url': '', 'birthday': '', 'note': '',
            'photo': None, 'photo_mime': 'image/jpeg', 'address': None,
            # The detail view shows the whole card; 'address' and 'url' above
            # stay as they are because the editor reads them.
            'addresses': [], 'urls': [], 'extra': [],
        }

        try:
            if 'n' in vcard_data.contents:
                contact['first_name'] = vcard_data.n.value.given or ''
                contact['last_name'] = vcard_data.n.value.family or ''
        except Exception:
            pass

        # Every instance is read, with the TYPE the editor manages. The first
        # of each also feeds the list row and the search haystack.
        try:
            contact['emails'] = [
                {'value': _as_str(line.value), 'type': read_type(line, MANAGED_EMAIL_TYPES)}
                for line in vcard_data.contents.get('email', [])
                if _as_str(line.value)
            ]
            if contact['emails']:
                contact['email'] = contact['emails'][0]['value']
        except Exception:
            pass

        try:
            contact['phones'] = [
                {'value': _as_str(line.value), 'type': read_type(line, MANAGED_TEL_TYPES)}
                for line in vcard_data.contents.get('tel', [])
                if _as_str(line.value)
            ]
            if contact['phones']:
                contact['phone'] = contact['phones'][0]['value']
        except Exception:
            pass

        try:
            if 'org' in vcard_data.contents:
                val = vcard_data.org.value
                # vobject encodes ORG as list-of-lists e.g. [['Acme','Dept']]
                if isinstance(val, list):
                    val = val[0] if val else ''
                if isinstance(val, list):
                    val = val[0] if val else ''
                contact['org'] = str(val) if val else ''
        except Exception:
            pass

        try:
            contact['urls'] = [
                text.strip('<>')
                for text in (_flatten_value(line.value)
                             for line in vcard_data.contents.get('url', []))
                if text
            ]
            if contact['urls']:
                contact['url'] = contact['urls'][0]
        except Exception:
            pass

        try:
            if 'bday' in vcard_data.contents:
                line = vcard_data.bday
                contact['birthday'] = normalize_birthday_to_display(
                    _as_str(line.value),
                    omit_year='X-APPLE-OMIT-YEAR' in line.params,
                )
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
                    detected = detect_image(photo)
                    contact['photo'] = base64.b64encode(photo).decode('utf-8')
                    # Serve the photo as what it actually is, not always JPEG.
                    contact['photo_mime'] = detected[1] if detected else 'image/jpeg'
        except Exception:
            pass

        # Every address, with all seven components. The editor writes only the
        # four it shows, but it preserves the rest, so the detail view reads
        # them all back.
        for line in vcard_data.contents.get('adr', []):
            # Per address, so one malformed one does not cost the others.
            try:
                value = line.value
                contact['addresses'].append({
                    'type': read_type(line, ADR_DISPLAY_TYPES),
                    'box': _flatten_value(getattr(value, 'box', '')),
                    'extended': _flatten_value(getattr(value, 'extended', '')),
                    'street': _flatten_value(getattr(value, 'street', '')),
                    'city': _flatten_value(getattr(value, 'city', '')),
                    'region': _flatten_value(getattr(value, 'region', '')),
                    'postal': _flatten_value(getattr(value, 'code', '')),
                    'country': _flatten_value(getattr(value, 'country', '')),
                })
            except Exception:
                continue

        # The shape the editor reads, kept unchanged.
        if contact['addresses']:
            first = contact['addresses'][0]
            contact['address'] = {
                'street': first['street'],
                'city': first['city'],
                'postal': first['postal'],
                'country': first['country'],
            }

        try:
            contact['extra'] = card_extra_fields(vcard_data)
        except Exception as e:
            logger.warning(f"Could not read the extra fields of {href}: {type(e).__name__}")

        # Compute initials from already-normalised string fields
        fi = _as_str(contact['first_name'])[:1]
        li = _as_str(contact['last_name'])[:1]
        contact['initials'] = (fi + li).upper() or _as_str(contact['name'])[:1].upper() or '?'

        # One haystack for the live filter, built here rather than assembled in
        # the browser, so every e-mail and phone number is searchable.
        haystack = [
            contact['name'], contact['first_name'], contact['last_name'],
            contact['org'], contact['url'], contact['birthday'], contact['note'],
        ]
        haystack += [e['value'] for e in contact['emails']]
        haystack += [p['value'] for p in contact['phones']]
        haystack += contact['urls']
        # The filter has to reach what the row no longer shows: every address
        # component, and every property the detail view lists.
        for address in contact['addresses']:
            haystack += [v for k, v in address.items() if k != 'type']
        haystack += [field['value'] for field in contact['extra']]
        contact['search'] = ' '.join(_as_str(v) for v in haystack if v).lower()

        contacts.append(contact)
        logger.debug(f"Parsed contact: {contact['name']} ({href})")

    return contacts


REPORT_BODY = '''<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
    <D:prop>
        <D:getetag/>
        <C:address-data/>
    </D:prop>
</C:addressbook-query>'''


def fetch_address_book(s: requests.Session, carddav_url: str) -> bytes:
    """Run the addressbook-query REPORT and return its body.

    Shared by the contact list, the export and the import's duplicate check.
    """
    resp = s.request(
        'REPORT', carddav_url,
        headers={'Depth': '1', 'Content-Type': 'application/xml; charset=utf-8'},
        data=REPORT_BODY.encode('utf-8'),
        timeout=CARDDAV_TIMEOUT
    )
    logger.info(f"REPORT → {resp.status_code}")
    if resp.status_code != 207:
        logger.error(f"REPORT failed: {resp.status_code} — {resp.text[:300]}")
        raise Exception(f"Could not read the address book (status {resp.status_code}).")
    return resp.content


def parse_raw_cards_from_report(response_content: bytes) -> List[str]:
    """The cards' own text, exactly as the server returned it.

    The export writes these bytes through untouched: round-tripping them
    through the parser would be a chance to lose something.
    """
    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(response_content)
    except ElementTree.ParseError as e:
        logger.error(f"Failed to parse REPORT XML: {e}")
        return []

    ns = {'D': 'DAV:', 'C': 'urn:ietf:params:xml:ns:carddav'}
    cards = []
    for elem in root.findall('.//D:response', ns):
        href_el = elem.find('.//D:href', ns)
        if href_el is None or not (href_el.text or '').endswith('.vcf'):
            continue
        address_data = elem.find('.//C:address-data', ns)
        if address_data is not None and address_data.text:
            cards.append(address_data.text.strip())
    return cards


def card_uids(raw_cards: List[str]) -> set:
    """The UIDs already in the address book, for skipping on import."""
    uids = set()
    for text in raw_cards:
        try:
            vobj = vobject.readOne(text)
            if 'uid' in vobj.contents:
                uid = _as_str(vobj.uid.value).strip()
                if uid:
                    uids.add(uid)
        except Exception:
            continue
    return uids


def _as_str(value) -> str:
    """Flatten any value (str, list, None) to a plain string."""
    if value is None:
        return ''
    if isinstance(value, list):
        flat = value[0] if value else ''
        return _as_str(flat)
    return str(value)


def _sort_key(value) -> tuple:
    """Return (0, normalized) for non-empty values, (1, '') for empty.
    Pushes blank fields to the end. Accepts str, list, or None."""
    v = _as_str(value).strip().lower()
    return (0, v) if v else (1, '')


def sort_contacts(contacts: list, sort_by: str = 'first_name') -> list:
    """Sort contacts. Empty fields are always pushed to the end."""
    if sort_by == 'last_name':
        key = lambda c: (
            _sort_key(c['last_name'] or c['name']),
            _sort_key(c['first_name']),
        )
    elif sort_by == 'org':
        key = lambda c: (
            _sort_key(c['org']),
            _sort_key(c['first_name'] or c['name']),
        )
    else:  # first_name (default)
        key = lambda c: (
            _sort_key(c['first_name'] or c['name']),
            _sort_key(c['last_name']),
        )
    try:
        return sorted(contacts, key=key)
    except Exception as e:
        logger.error(f"Sort error: {e}")
        return contacts


def _collect_typed_rows(form, field: str, managed: Tuple[str, ...]) -> List[dict]:
    """Read the repeated value/type rows of one multi-valued field.

    The two lists arrive in the order the rows appear, so a value keeps the
    type selected beside it. A row left blank is dropped.
    """
    values = form.getlist(field)
    types = form.getlist(f"{field}_type")
    rows = []
    for index, value in enumerate(values):
        value = value.strip()
        if not value:
            continue
        chosen = types[index].strip().upper() if index < len(types) else ''
        rows.append({'value': value, 'type': chosen if chosen in managed else ''})
    return rows


def collect_vcard_data_from_form(form, files=None) -> dict:
    """Read the editor's fields off the form.

    Every editable field is always present, empty string included: an empty
    value means the user cleared it, which removes that property from the card.
    PHOTO is the exception — it is absent unless a file was uploaded, so an
    unchanged photo is left alone.
    """
    first_name = form.get('first_name', '').strip()
    last_name = form.get('last_name', '').strip()
    bday = form.get('birthday', '').strip()

    data = {
        'FN': f"{first_name} {last_name}".strip(),
        'FIRST_NAME': first_name,
        'LAST_NAME': last_name,
        'EMAILS': _collect_typed_rows(form, 'email', MANAGED_EMAIL_TYPES),
        'TELS': _collect_typed_rows(form, 'phone', MANAGED_TEL_TYPES),
        'ORG': form.get('organization', '').strip(),
        'URL': form.get('url', '').strip(),
        'NOTE': form.get('note', '').strip(),
        'BDAY': normalize_birthday_to_iso(bday) if bday else '',
        'ADR': {
            'street': form.get('street', '').strip(),
            'city': form.get('city', '').strip(),
            'postal': form.get('postal', '').strip(),
            'country': form.get('country', '').strip(),
        },
    }

    if form.get('remove_photo') == '1':
        data['REMOVE_PHOTO'] = True

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
    if not is_signed_in():
        return redirect(url_for('login'))
    return redirect(url_for('contacts'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_signed_in():
        return redirect(url_for('contacts'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter a username and password.', 'error')
            return render_template('login.html')

        if check_auth(username, password):
            sid = SESSIONS.create(username, password)
            if sid is None:
                flash('The server is handling too many sessions. Try again later.', 'error')
                return render_template('login.html')
            # A fresh cookie and CSRF token on sign-in, against session fixation.
            session.clear()
            session['sid'] = sid
            generate_csrf_token()
            logger.info("User logged in successfully.")
            return redirect(url_for('contacts'))

        logger.warning("Failed login attempt.")
        flash('Invalid credentials or access denied by the CardDAV server.', 'error')
        return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    # Revoke the session server-side, so its credentials are gone from memory.
    SESSIONS.destroy(session.get('sid', ''))
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
        resp = s.request('PROPFIND', carddav_url, headers={'Depth': '1'}, timeout=CARDDAV_TIMEOUT)
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

    # Sort preference: query string > session > default
    # Read before POST handling so redirect preserves it
    sort_by = request.args.get('sort') or session.get('sort_by', 'first_name')
    valid_sorts = {'first_name', 'last_name', 'org'}
    if sort_by not in valid_sorts:
        sort_by = 'first_name'
    session['sort_by'] = sort_by

    if request.method == 'POST':
        if not validate_csrf():
            flash('Invalid request (CSRF).', 'error')
            return redirect(url_for('contacts', sort=sort_by))
        try:
            vcard_data = collect_vcard_data_from_form(request.form, request.files)
            vcard_content = build_new_vcard(vcard_data)
            filename = f"{base64.urlsafe_b64encode(os.urandom(12)).decode()}.vcf"
            put_url = f"{carddav_url.rstrip('/')}/{filename}"
            resp = s.put(
                put_url,
                data=vcard_content.encode('utf-8'),
                # If-None-Match: * creates only if nothing is already there.
                headers={'Content-Type': 'text/vcard; charset=utf-8', 'If-None-Match': '*'},
                timeout=CARDDAV_TIMEOUT
            )
            if resp.status_code == 412:
                raise Exception("A contact already exists at that address. Try again.")
            if resp.status_code == 413:
                raise Exception(
                    "The CardDAV server refused the contact for its size. "
                    "A smaller photo should fit."
                )
            if resp.status_code not in (201, 204):
                raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")
            flash('Contact created successfully.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            flash(f"Error creating contact: {e}", 'error')
        return redirect(url_for('contacts', sort=sort_by))

    contact_list = []
    try:
        contact_list = parse_contacts_from_report(fetch_address_book(s, carddav_url))
        contact_list = sort_contacts(contact_list, sort_by)
        logger.info(f"Loaded {len(contact_list)} contacts.")
    except Exception as e:
        logger.error(f"Error listing contacts: {e}")
        flash(f"Error: {e}", 'error')

    return render_template(
        'index.html',
        contacts=contact_list,
        sort_by=sort_by,
        email_types=MANAGED_EMAIL_TYPES,
        tel_types=MANAGED_TEL_TYPES,
    )


@app.route('/contacts/export')
@check_login_required
def export_contacts():
    """Download the whole address book as one .vcf file."""
    s = get_user_session()
    try:
        raw_cards = parse_raw_cards_from_report(fetch_address_book(s, get_user_carddav_url()))
    except Exception as e:
        logger.error(f"Export failed: {e}")
        flash(f"Could not export: {e}", 'error')
        return redirect(url_for('contacts'))

    if not raw_cards:
        flash('There is nothing to export.', 'message')
        return redirect(url_for('contacts'))

    # The cards go out as the server stored them, unparsed.
    body = '\r\n'.join(raw_cards) + '\r\n'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    filename = f"contacts-{g.username}-{stamp}.vcf"
    logger.info(f"Exported {len(raw_cards)} contacts.")
    return Response(
        body.encode('utf-8'),
        mimetype='text/vcard; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.route('/contacts/import', methods=['POST'])
@check_login_required
def import_contacts():
    """Add the cards of an uploaded .vcf file that are not already here.

    A card whose UID is already in the book is skipped rather than merged:
    overwriting someone's contact with a stale copy from a file is worse than
    doing nothing, and there is no conflict UI for a bulk operation.
    """
    if not validate_csrf():
        flash('Invalid request (CSRF).', 'error')
        return redirect(url_for('contacts'))

    upload = request.files.get('vcf')
    if not upload or not upload.filename:
        flash('Choose a .vcf file to import.', 'error')
        return redirect(url_for('contacts'))

    s = get_user_session()
    carddav_url = get_user_carddav_url()

    try:
        text = upload.read().decode('utf-8', errors='replace')
        existing = card_uids(parse_raw_cards_from_report(fetch_address_book(s, carddav_url)))
    except Exception as e:
        logger.error(f"Import could not start: {e}")
        flash(f"Could not import: {e}", 'error')
        return redirect(url_for('contacts'))

    added = skipped = failed = 0
    try:
        cards = list(vobject.readComponents(text, ignoreUnreadable=True))
    except Exception as e:
        logger.error(f"Import could not parse the file: {e}")
        flash('That file could not be read as vCard.', 'error')
        return redirect(url_for('contacts'))

    for vobj in cards:
        try:
            if 'uid' in vobj.contents:
                uid = _as_str(vobj.uid.value).strip()
            else:
                uid = str(uuid.uuid4())
                vobj.add('uid').value = uid
            if uid in existing:
                skipped += 1
                continue

            filename = f"{base64.urlsafe_b64encode(os.urandom(12)).decode()}.vcf"
            resp = s.put(
                f"{carddav_url.rstrip('/')}/{filename}",
                data=vobj.serialize(validate=False).encode('utf-8'),
                headers={'Content-Type': 'text/vcard; charset=utf-8', 'If-None-Match': '*'},
                timeout=CARDDAV_TIMEOUT
            )
            if resp.status_code in (201, 204):
                added += 1
                existing.add(uid)
            else:
                failed += 1
                logger.warning(f"Import rejected a card: status {resp.status_code}")
        except Exception as e:
            failed += 1
            logger.warning(f"Import skipped a card: {type(e).__name__}")

    parts = [f"{added} added"]
    if skipped:
        parts.append(f"{skipped} already here")
    if failed:
        parts.append(f"{failed} could not be read")
    flash(f"Import finished: {', '.join(parts)}.", 'error' if failed and not added else 'success')
    logger.info(f"Import: {added} added, {skipped} skipped, {failed} failed.")
    return redirect(url_for('contacts', sort=session.get('sort_by', 'first_name')))


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

        # The version the user actually saw and edited. Writing without it
        # would silently overwrite a change synced from another device.
        etag = request.form.get('etag', '').strip()
        if not etag:
            raise Exception(
                "This contact has no version tag, so it cannot be saved safely. "
                "Reload the page and try again."
            )

        contact_url = f"{carddav_url.rstrip('/')}/{contact_id}"

        existing_resp = s.get(contact_url, timeout=CARDDAV_TIMEOUT)
        if existing_resp.status_code != 200:
            raise Exception(f"Could not fetch contact: status {existing_resp.status_code}")

        try:
            # The parsed card is the base for the save: the form's fields are
            # applied onto it, and every other property is written back as-is.
            vobj = vobject.readOne(existing_resp.text)
        except Exception as parse_err:
            raise Exception(f"Could not parse existing vCard: {parse_err}")

        vcard_data = collect_vcard_data_from_form(request.form, request.files)
        vcard_content = serialize_updated_vcard(vobj, vcard_data)

        resp = s.put(
            contact_url,
            data=vcard_content.encode('utf-8'),
            headers={'Content-Type': 'text/vcard; charset=utf-8', 'If-Match': etag},
            timeout=CARDDAV_TIMEOUT
        )
        if resp.status_code == 412:
            flash(
                'This contact was changed somewhere else since you opened this page. '
                'Nothing was saved — reload and make your change again.', 'error'
            )
            return redirect(url_for('contacts', sort=session.get('sort_by', 'first_name')))
        if resp.status_code == 413:
            raise Exception(
                "The CardDAV server refused the contact for its size. "
                "A smaller photo should fit."
            )
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Status {resp.status_code}: {resp.text[:200]}")

        flash('Contact updated successfully.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        flash(f"Error updating contact: {e}", 'error')

    return redirect(url_for('contacts', sort=session.get('sort_by', 'first_name')))


@app.route('/contacts/<contact_id>/delete', methods=['POST'])
@check_login_required
def delete_contact(contact_id):
    if not validate_csrf():
        flash('Invalid request (CSRF).', 'error')
        return redirect(url_for('contacts'))

    s = get_user_session()
    carddav_url = get_user_carddav_url()

    try:
        etag = request.form.get('etag', '').strip()
        if not etag:
            raise Exception(
                "This contact has no version tag, so it cannot be deleted safely. "
                "Reload the page and try again."
            )

        contact_url = f"{carddav_url.rstrip('/')}/{contact_id}"
        resp = s.delete(contact_url, headers={'If-Match': etag}, timeout=CARDDAV_TIMEOUT)
        if resp.status_code == 412:
            flash(
                'This contact was changed somewhere else since you opened this page. '
                'Nothing was deleted — reload to see the current version.', 'error'
            )
            return redirect(url_for('contacts', sort=session.get('sort_by', 'first_name')))
        if resp.status_code not in (200, 204):
            raise Exception(f"Status {resp.status_code}")
        flash('Contact deleted.', 'success')
    except Exception as e:
        logger.error(f"Error deleting contact: {e}")
        flash(f"Error deleting contact: {e}", 'error')

    return redirect(url_for('contacts', sort=session.get('sort_by', 'first_name')))


if __name__ == '__main__':
    # Development only — production runs via gunicorn (see Dockerfile)
    app.run(host='0.0.0.0', port=5000, debug=False)