#!/usr/bin/env python3
"""Round-trip tests for the vCard write path and the photo pipeline.

Data loss is the worst failure mode for a contacts editor, so these tests
assert that saving a contact keeps every property the editor does not show:
additional e-mails and phone numbers, the TYPE parameters it does not manage,
group memberships, and X-* extensions.

No test framework needed — run it directly:

    python tests/test_vcard_roundtrip.py
"""

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

import vobject  # noqa: E402
from PIL import Image  # noqa: E402

from app import (  # noqa: E402
    MANAGED_EMAIL_TYPES,
    MANAGED_TEL_TYPES,
    apply_contact_fields,
    build_new_vcard,
    detect_image,
    normalize_birthday_to_display,
    normalize_birthday_to_iso,
    normalize_photo,
    read_type,
    serialize_updated_vcard,
)

# A card with the kind of content Apple Contacts and DAVx5 actually write.
# The first e-mail carries INTERNET and PREF alongside WORK: the editor owns
# only WORK, and the other two must survive a save.
RICH_CARD = """BEGIN:VCARD\r
VERSION:3.0\r
UID:test-uid-1234\r
FN:Jean Dupont\r
N:Dupont;Jean;Marie;Dr.;PhD\r
NICKNAME:Jeannot\r
ORG:Acme Corp;R&D;Team 4\r
TITLE:Senior Engineer\r
ROLE:Developer\r
EMAIL;TYPE=INTERNET,PREF,WORK:jean@acme.example\r
EMAIL;TYPE=HOME:jean@home.example\r
EMAIL;TYPE=OTHER:jean.dupont@old.example\r
TEL;TYPE=CELL:+33600000001\r
TEL;TYPE=VOICE,WORK:+33100000002\r
TEL;TYPE=FAX:+33100000003\r
ADR;TYPE=HOME:PoBox 42;Apt 7;1 rue de la Paix;Paris;Ile-de-France;75001;France\r
URL:https://example.org\r
BDAY:1980-05-17\r
NOTE:Met at a conference\r
CATEGORIES:Friends,Work\r
IMPP;TYPE=xmpp:xmpp:jean@chat.example\r
X-PHONETIC-FIRST-NAME:Jahn\r
X-CUSTOM-FIELD:keep me\r
REV:20200101T120000Z\r
END:VCARD\r
"""

# What the editor submits when only the surname was changed: every row comes
# back exactly as the UI displayed it.
UNCHANGED_FORM = {
    'FN': 'Jean Martin',
    'FIRST_NAME': 'Jean',
    'LAST_NAME': 'Martin',
    'EMAILS': [
        {'value': 'jean@acme.example', 'type': 'WORK'},
        {'value': 'jean@home.example', 'type': 'HOME'},
        {'value': 'jean.dupont@old.example', 'type': 'OTHER'},
    ],
    'TELS': [
        {'value': '+33600000001', 'type': 'CELL'},
        {'value': '+33100000002', 'type': 'WORK'},
        {'value': '+33100000003', 'type': 'FAX'},
    ],
    'ORG': 'Acme Corp',
    'URL': 'https://example.org',
    'BDAY': '1980-05-17',
    'NOTE': 'Met at a conference',
    'ADR': {
        'street': '1 rue de la Paix',
        'city': 'Paris',
        'postal': '75001',
        'country': 'France',
    },
}

FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ''))
        FAILURES.append(label)


def save(card, form):
    """Run a card and a form through the write path, return the reparsed card."""
    return vobject.readOne(serialize_updated_vcard(vobject.readOne(card), form))


def values(vobj, name):
    return [line.value for line in vobj.contents.get(name, [])]


def types_of(vobj, name):
    return [line.params.get('TYPE', []) for line in vobj.contents.get(name, [])]


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------

def test_unshown_properties_survive():
    print("\nProperties the editor never shows survive a save")
    out = save(RICH_CARD, UNCHANGED_FORM)

    for prop, expected in [
        ('nickname', 'Jeannot'),
        ('title', 'Senior Engineer'),
        ('role', 'Developer'),
        ('x-phonetic-first-name', 'Jahn'),
        ('x-custom-field', 'keep me'),
    ]:
        check(f"{prop.upper()} kept", values(out, prop) == [expected], values(out, prop))

    check('CATEGORIES kept', 'categories' in out.contents, list(out.contents))
    check('IMPP kept', values(out, 'impp') == ['xmpp:jean@chat.example'], values(out, 'impp'))
    check('UID unchanged', values(out, 'uid') == ['test-uid-1234'], values(out, 'uid'))


def test_all_instances_and_their_types_survive():
    print("\nEvery e-mail and phone number keeps its place and its parameters")
    out = save(RICH_CARD, UNCHANGED_FORM)

    emails = values(out, 'email')
    check('all 3 e-mails kept', len(emails) == 3, f"got {len(emails)}: {emails}")
    check('order preserved', emails[0] == 'jean@acme.example', emails)

    tels = values(out, 'tel')
    check('all 3 phone numbers kept', len(tels) == 3, f"got {len(tels)}: {tels}")

    email_types = types_of(out, 'email')
    check('managed TYPE written', 'WORK' in email_types[0], email_types[0])
    check('unmanaged INTERNET kept', 'INTERNET' in email_types[0], email_types[0])
    check('unmanaged PREF kept', 'PREF' in email_types[0], email_types[0])

    tel_types = types_of(out, 'tel')
    check('unmanaged VOICE kept', 'VOICE' in tel_types[1], tel_types[1])
    check('managed WORK kept', 'WORK' in tel_types[1], tel_types[1])


def test_structured_components_survive():
    print("\nStructured values keep the components the editor does not expose")
    out = save(RICH_CARD, UNCHANGED_FORM)

    n = out.n.value
    check('N family updated', n.family == 'Martin', n.family)
    check('N given updated', n.given == 'Jean', n.given)
    check('N middle name kept', n.additional == 'Marie', n.additional)
    check('N prefix kept', n.prefix == 'Dr.', n.prefix)
    check('N suffix kept', n.suffix == 'PhD', n.suffix)

    adr = out.adr.value
    check('ADR street updated', adr.street == '1 rue de la Paix', adr.street)
    check('ADR post box kept', adr.box == 'PoBox 42', adr.box)
    check('ADR extended kept', adr.extended == 'Apt 7', adr.extended)
    check('ADR region kept', adr.region == 'Ile-de-France', adr.region)

    check('ORG sub-units kept', out.org.value == ['Acme Corp', 'R&D', 'Team 4'], out.org.value)


def test_editing_one_row_leaves_the_others():
    print("\nEditing one row changes only that row")
    form = dict(UNCHANGED_FORM)
    form['EMAILS'] = [
        {'value': 'jean.martin@acme.example', 'type': 'WORK'},
        {'value': 'jean@home.example', 'type': 'HOME'},
        {'value': 'jean.dupont@old.example', 'type': 'OTHER'},
    ]
    out = save(RICH_CARD, form)

    emails = values(out, 'email')
    check('edited value applied', emails[0] == 'jean.martin@acme.example', emails)
    check('others untouched', emails[1:] == ['jean@home.example', 'jean.dupont@old.example'], emails)
    check('still 3 e-mails', len(emails) == 3, len(emails))
    check('its unmanaged params kept', 'PREF' in types_of(out, 'email')[0], types_of(out, 'email')[0])


def test_removing_a_row_removes_one_property():
    print("\nRemoving a row removes one instance, not the rest")
    form = dict(UNCHANGED_FORM)
    form['EMAILS'] = [{'value': 'jean@acme.example', 'type': 'WORK'}]
    form['TELS'] = []
    out = save(RICH_CARD, form)

    check('two e-mails removed', values(out, 'email') == ['jean@acme.example'], values(out, 'email'))
    check('all phones removed', 'tel' not in out.contents, values(out, 'tel'))
    check('unrelated field intact', values(out, 'nickname') == ['Jeannot'], values(out, 'nickname'))


def test_adding_a_row_adds_a_property():
    print("\nAdding a row adds an instance")
    form = dict(UNCHANGED_FORM)
    form['EMAILS'] = UNCHANGED_FORM['EMAILS'] + [{'value': 'new@example.org', 'type': 'OTHER'}]
    out = save(RICH_CARD, form)

    emails = values(out, 'email')
    check('4 e-mails now', len(emails) == 4, f"got {len(emails)}: {emails}")
    check('new value last', emails[3] == 'new@example.org', emails)
    check('new TYPE written', 'OTHER' in types_of(out, 'email')[3], types_of(out, 'email')[3])


def test_clearing_a_field_removes_the_property():
    print("\nClearing a field removes that property")
    form = dict(UNCHANGED_FORM, NOTE='', URL='')
    out = save(RICH_CARD, form)

    check('NOTE removed', 'note' not in out.contents, values(out, 'note'))
    check('URL removed', 'url' not in out.contents, values(out, 'url'))
    check('unrelated field still there', values(out, 'bday') == ['1980-05-17'], values(out, 'bday'))


def test_special_characters_are_escaped():
    print("\nSemicolons and commas in text values survive")
    form = dict(
        UNCHANGED_FORM,
        ORG='Smith; Jones, Partners',
        NOTE='Line one; still line one, really\nLine two',
    )
    out = save(RICH_CARD, form)

    check(
        'semicolon in ORG not a component break',
        out.org.value[0] == 'Smith; Jones, Partners',
        out.org.value,
    )
    check(
        'semicolon and comma in NOTE intact',
        out.note.value == 'Line one; still line one, really\nLine two',
        repr(out.note.value),
    )
    check('ORG sub-units still kept', out.org.value[1:] == ['R&D', 'Team 4'], out.org.value)


def test_rev_moves_forward():
    print("\nREV marks the card as changed")
    out = save(RICH_CARD, UNCHANGED_FORM)
    rev = values(out, 'rev')
    check('REV updated', rev and rev[0] != '20200101T120000Z', rev)
    check('REV looks like a timestamp', rev and rev[0].endswith('Z') and len(rev[0]) == 16, rev)


# ---------------------------------------------------------------------------
# Birthdays
# ---------------------------------------------------------------------------

def test_birthday_display():
    print("\nBirthdays are displayed in every form found in the wild")
    cases = [
        ('1980-05-17', False, '17/05/1980'),
        ('19800517', False, '17/05/1980'),
        ('--0517', False, '17/05'),          # vCard's own year-less form
        ('--05-17', False, '17/05'),
        ('1604-05-17', True, '17/05'),       # Apple, with the marker
        ('1604-05-17', False, '17/05'),      # iOS, without the marker
        ('', False, ''),
    ]
    for stored, omit, expected in cases:
        got = normalize_birthday_to_display(stored, omit)
        check(f"{stored or '(empty)'} -> {expected or '(empty)'}", got == expected, repr(got))

    # Anything unrecognised is shown as stored rather than mangled.
    check(
        'unknown form passed through',
        normalize_birthday_to_display('1980-05-17T00:00:00Z') == '1980-05-17T00:00:00Z',
        normalize_birthday_to_display('1980-05-17T00:00:00Z'),
    )


def test_birthday_storage():
    print("\nBirthdays typed into the form are stored correctly")
    check('full date', normalize_birthday_to_iso('17/05/1980') == '1980-05-17',
          normalize_birthday_to_iso('17/05/1980'))
    check('unpadded date', normalize_birthday_to_iso('7/5/1980') == '1980-05-07',
          normalize_birthday_to_iso('7/5/1980'))
    check('no year -> --MMDD', normalize_birthday_to_iso('17/05') == '--0517',
          normalize_birthday_to_iso('17/05'))
    check('empty stays empty', normalize_birthday_to_iso('') == '', repr(normalize_birthday_to_iso('')))


def test_apple_birthday_keeps_its_form():
    print("\nA year-less birthday keeps the form its card already used")
    apple = (
        "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bob\r\n"
        "BDAY;X-APPLE-OMIT-YEAR=1604:1604-05-17\r\nEND:VCARD\r\n"
    )
    form = {
        'FN': 'Bob', 'FIRST_NAME': 'Bob', 'LAST_NAME': '',
        'EMAILS': [], 'TELS': [], 'ORG': '', 'URL': '', 'NOTE': '',
        'BDAY': '--0517',
        'ADR': {'street': '', 'city': '', 'postal': '', 'country': ''},
    }
    out = save(apple, form)
    check('Apple form kept', values(out, 'bday') == ['1604-05-17'], values(out, 'bday'))
    check('marker kept', 'X-APPLE-OMIT-YEAR' in out.bday.params, out.bday.params)

    # A real year supplied later drops the marker.
    out2 = save(apple, dict(form, BDAY='1980-05-17'))
    check('real year stored', values(out2, 'bday') == ['1980-05-17'], values(out2, 'bday'))
    check('marker dropped', 'X-APPLE-OMIT-YEAR' not in out2.bday.params, out2.bday.params)

    # A card with no Apple history uses vCard's own form.
    plain = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bob\r\nBDAY:1980-05-17\r\nEND:VCARD\r\n"
    out3 = save(plain, form)
    check('plain card uses --MMDD', values(out3, 'bday') == ['--0517'], values(out3, 'bday'))


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def make_image(width, height, mode='RGB', fmt='JPEG', orientation=None, metadata=False):
    """An image, optionally carrying the EXIF a camera would attach.

    A nested IFD such as GPS cannot be assigned as a plain dict: Pillow types
    tag 0x8825 as a LONG offset and fails to pack a dict into it. It has to go
    through get_ifd(), and that is wrapped so a Pillow quirk breaks neither
    fixture nor test.
    """
    fill = (120, 160, 200) if mode == 'RGB' else (120, 160, 200, 255)
    image = Image.new(mode, (width, height), fill)

    kwargs = {}
    if orientation is not None or metadata:
        exif = Image.Exif()
        if orientation is not None:
            exif[0x0112] = orientation       # Orientation
        if metadata:
            exif[0x010F] = 'TestCamera'      # Make, an IFD0 string tag
            exif[0x0110] = 'TestModel'       # Model
            try:
                gps = exif.get_ifd(0x8825)
                gps[1] = 'N'                 # GPSLatitudeRef
                gps[2] = ((48, 1), (51, 1), (0, 1))  # GPSLatitude
            except Exception:
                pass
        kwargs['exif'] = exif.tobytes()

    buf = io.BytesIO()
    image.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def exif_of(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as image:
        return dict(image.getexif())


def test_photo_metadata_is_stripped():
    print("\nAn uploaded photo loses its metadata")
    original = make_image(800, 600, orientation=1, metadata=True)

    # Confirm the fixture carries what the test claims to strip, so a broken
    # fixture is reported as one rather than as a passing strip.
    before = exif_of(original)
    check('fixture carries EXIF', bool(before), before)
    check('fixture carries the camera make', before.get(0x010F) == 'TestCamera', before.get(0x010F))

    normalized, vcard_type, mime = normalize_photo(original)
    check('no EXIF in the result', not exif_of(normalized), exif_of(normalized))
    check('camera make gone from the bytes', b'TestCamera' not in normalized)
    check('camera model gone from the bytes', b'TestModel' not in normalized)
    check('type is JPEG', (vcard_type, mime) == ('JPEG', 'image/jpeg'), (vcard_type, mime))


def test_photo_orientation_is_applied():
    print("\nA rotated photo is straightened")
    # Orientation 6 means "rotate 90 CW to display": 800x400 shows as 400x800.
    rotated = make_image(800, 400, orientation=6)
    check('fixture carries orientation 6', exif_of(rotated).get(0x0112) == 6, exif_of(rotated))

    normalized, _, _ = normalize_photo(rotated)
    with Image.open(io.BytesIO(normalized)) as out:
        size = out.size
    check('width and height swapped', size == (400, 800), size)
    check('orientation tag not carried over', not exif_of(normalized), exif_of(normalized))


def test_photo_is_bounded():
    print("\nA large photo is scaled into the budget")
    big = make_image(4000, 3000)
    normalized, _, _ = normalize_photo(big)
    with Image.open(io.BytesIO(normalized)) as out:
        width, height = out.size
    check('longest side at most 1024', max(width, height) <= 1024, (width, height))
    check('at most 512 KB', len(normalized) <= 512 * 1024, f"{len(normalized)} bytes")
    check('much smaller than the original', len(normalized) < len(big), (len(normalized), len(big)))


def test_photo_keeps_transparency_as_png():
    print("\nTransparency is kept, as PNG")
    transparent = make_image(300, 300, mode='RGBA', fmt='PNG')
    normalized, vcard_type, mime = normalize_photo(transparent)
    check('stored as PNG', (vcard_type, mime) == ('PNG', 'image/png'), (vcard_type, mime))
    with Image.open(io.BytesIO(normalized)) as out:
        check('alpha channel kept', out.mode in ('RGBA', 'LA', 'P'), out.mode)


def test_photo_rejects_what_is_not_an_image():
    print("\nA file that is not an image is refused")
    try:
        normalize_photo(b'definitely not an image')
        check('non-image raises', False, 'no exception')
    except ValueError:
        check('non-image raises', True)


def test_photo_round_trips_through_a_card():
    print("\nA photo survives being written to a card and read back")
    png = make_image(200, 200, mode='RGBA', fmt='PNG')
    normalized, _, _ = normalize_photo(png)

    out = save(RICH_CARD, dict(UNCHANGED_FORM, PHOTO=png))
    check('PNG stored as TYPE=PNG', out.photo.params.get('TYPE') == ['PNG'], out.photo.params)
    check('bytes are the normalized ones', out.photo.value == normalized, 'bytes differ')

    # An edit that does not touch the photo must leave it alone.
    kept = save(out.serialize(validate=False), UNCHANGED_FORM)
    check('photo kept when not re-uploaded', kept.photo.value == normalized, 'photo changed')

    # Ticking "remove the photo" drops it.
    removed = save(out.serialize(validate=False), dict(UNCHANGED_FORM, REMOVE_PHOTO=True))
    check('photo removed on request', 'photo' not in removed.contents, list(removed.contents))


def test_read_photo_type_detection():
    print("\nA stored photo is served as what it actually is")
    cases = [
        (b'\xff\xd8\xff' + b'\x00' * 40, ('JPEG', 'image/jpeg')),
        (b'\x89PNG\r\n\x1a\n' + b'\x00' * 40, ('PNG', 'image/png')),
        (b'GIF89a' + b'\x00' * 40, ('GIF', 'image/gif')),
        (b'RIFF' + b'\x00' * 4 + b'WEBP' + b'\x00' * 32, ('WEBP', 'image/webp')),
    ]
    for data, expected in cases:
        check(f"{expected[0]} detected", detect_image(data) == expected, detect_image(data))
    check('not an image -> None', detect_image(b'nope') is None, detect_image(b'nope'))


# ---------------------------------------------------------------------------
# TYPE parameter handling
# ---------------------------------------------------------------------------

def test_type_reading():
    print("\nOnly the TYPE tokens the editor manages are reported")
    card = vobject.readOne(RICH_CARD)
    emails = card.contents['email']
    check('WORK read past INTERNET and PREF',
          read_type(emails[0], MANAGED_EMAIL_TYPES) == 'WORK',
          read_type(emails[0], MANAGED_EMAIL_TYPES))
    check('HOME read', read_type(emails[1], MANAGED_EMAIL_TYPES) == 'HOME',
          read_type(emails[1], MANAGED_EMAIL_TYPES))
    tels = card.contents['tel']
    check('CELL read', read_type(tels[0], MANAGED_TEL_TYPES) == 'CELL',
          read_type(tels[0], MANAGED_TEL_TYPES))
    check('VOICE is not managed, WORK is',
          read_type(tels[1], MANAGED_TEL_TYPES) == 'WORK',
          read_type(tels[1], MANAGED_TEL_TYPES))


def test_clearing_a_type_keeps_the_rest():
    print("\nClearing the type dropdown keeps the unmanaged tokens")
    form = dict(UNCHANGED_FORM)
    form['EMAILS'] = [{'value': 'jean@acme.example', 'type': ''}]
    out = save(RICH_CARD, form)
    tokens = out.contents['email'][0].params.get('TYPE', [])
    check('WORK gone', 'WORK' not in tokens, tokens)
    check('INTERNET kept', 'INTERNET' in tokens, tokens)
    check('PREF kept', 'PREF' in tokens, tokens)


# ---------------------------------------------------------------------------
# New and minimal cards
# ---------------------------------------------------------------------------

def test_new_card_is_valid():
    print("\nA new card is well formed")
    text = build_new_vcard({
        'FN': 'Ada Lovelace',
        'FIRST_NAME': 'Ada',
        'LAST_NAME': 'Lovelace',
        'EMAILS': [{'value': 'ada@example.org', 'type': 'HOME'}],
        'TELS': [],
        'ORG': 'Analytical Engines; Ltd',
        'URL': '',
        'BDAY': '1815-12-10',
        'NOTE': '',
        'ADR': {'street': '', 'city': 'London', 'postal': '', 'country': ''},
    })
    out = vobject.readOne(text)

    check('VERSION is 3.0', values(out, 'version') == ['3.0'], values(out, 'version'))
    check('FN set', values(out, 'fn') == ['Ada Lovelace'], values(out, 'fn'))
    check('N set', out.n.value.family == 'Lovelace' and out.n.value.given == 'Ada', str(out.n.value))
    check('UID generated', bool(values(out, 'uid')), values(out, 'uid'))
    check('e-mail with its type', values(out, 'email') == ['ada@example.org'], values(out, 'email'))
    check('TYPE written', out.email.params.get('TYPE') == ['HOME'], out.email.params)
    check('empty fields left out', 'tel' not in out.contents, values(out, 'tel'))
    check('city kept without street', out.adr.value.city == 'London', out.adr.value.city)
    check('semicolon in ORG escaped', out.org.value[0] == 'Analytical Engines; Ltd', out.org.value)


def test_a_name_is_required():
    print("\nA card without a name is refused")
    try:
        apply_contact_fields(vobject.vCard(), {'FN': '  ', 'FIRST_NAME': '', 'LAST_NAME': ''})
        check('empty name raises', False, 'no exception')
    except ValueError:
        check('empty name raises', True)


def test_minimal_card_still_saves():
    print("\nA card with almost nothing in it still saves")
    minimal = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bob\r\nEND:VCARD\r\n"
    out = save(minimal, {
        'FN': 'Bob Smith',
        'FIRST_NAME': 'Bob',
        'LAST_NAME': 'Smith',
        'EMAILS': [{'value': 'bob@example.org', 'type': ''}],
        'TELS': [],
        'ORG': '', 'URL': '', 'BDAY': '', 'NOTE': '',
        'ADR': {'street': '', 'city': '', 'postal': '', 'country': ''},
    })
    check('FN updated', values(out, 'fn') == ['Bob Smith'], values(out, 'fn'))
    check('N created', out.n.value.family == 'Smith', str(out.n.value))
    check('e-mail added', values(out, 'email') == ['bob@example.org'], values(out, 'email'))
    check('no TYPE when none chosen', 'TYPE' not in out.email.params, out.email.params)
    check('no empty ADR added', 'adr' not in out.contents, values(out, 'adr'))


def main():
    for test in [
        test_unshown_properties_survive,
        test_all_instances_and_their_types_survive,
        test_structured_components_survive,
        test_editing_one_row_leaves_the_others,
        test_removing_a_row_removes_one_property,
        test_adding_a_row_adds_a_property,
        test_clearing_a_field_removes_the_property,
        test_special_characters_are_escaped,
        test_rev_moves_forward,
        test_birthday_display,
        test_birthday_storage,
        test_apple_birthday_keeps_its_form,
        test_photo_metadata_is_stripped,
        test_photo_orientation_is_applied,
        test_photo_is_bounded,
        test_photo_keeps_transparency_as_png,
        test_photo_rejects_what_is_not_an_image,
        test_photo_round_trips_through_a_card,
        test_read_photo_type_detection,
        test_type_reading,
        test_clearing_a_type_keeps_the_rest,
        test_new_card_is_valid,
        test_a_name_is_required,
        test_minimal_card_still_saves,
    ]:
        try:
            test()
        except Exception as e:  # a crash is a failure, not an interruption
            print(f"  FAIL {test.__name__} raised {type(e).__name__}: {e}")
            FAILURES.append(test.__name__)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
