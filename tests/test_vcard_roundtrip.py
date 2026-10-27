#!/usr/bin/env python3
"""Round-trip tests for the vCard write path.

Data loss is the worst failure mode for a contacts editor, so these tests
assert that saving a contact from the UI keeps every property the editor does
not show: additional e-mails and phone numbers, their TYPE parameters, group
memberships, and X-* extensions.

No test framework needed — run it directly:

    python tests/test_vcard_roundtrip.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

import vobject  # noqa: E402

from app import (  # noqa: E402
    apply_contact_fields,
    build_new_vcard,
    detect_image,
    serialize_updated_vcard,
)

# A card with the kind of content Apple Contacts and DAVx5 actually write.
RICH_CARD = """BEGIN:VCARD\r
VERSION:3.0\r
UID:test-uid-1234\r
FN:Jean Dupont\r
N:Dupont;Jean;Marie;Dr.;PhD\r
NICKNAME:Jeannot\r
ORG:Acme Corp;R&D;Team 4\r
TITLE:Senior Engineer\r
ROLE:Developer\r
EMAIL;TYPE=WORK:jean@acme.example\r
EMAIL;TYPE=HOME:jean@home.example\r
EMAIL;TYPE=OTHER:jean.dupont@old.example\r
TEL;TYPE=CELL:+33600000001\r
TEL;TYPE=WORK:+33100000002\r
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

# What the editor submits when only the surname was changed: every other field
# comes back exactly as the UI displayed it (the first of each multi-valued
# property).
UNCHANGED_FORM = {
    'FN': 'Jean Martin',
    'FIRST_NAME': 'Jean',
    'LAST_NAME': 'Martin',
    'EMAIL': 'jean@acme.example',
    'TEL': '+33600000001',
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

    check('CATEGORIES kept', 'categories' in out.contents, out.contents.keys())
    check('IMPP kept', values(out, 'impp') == ['xmpp:jean@chat.example'], values(out, 'impp'))
    check('UID unchanged', values(out, 'uid') == ['test-uid-1234'], values(out, 'uid'))


def test_additional_emails_and_phones_survive():
    print("\nMulti-valued properties keep every instance and its parameters")
    out = save(RICH_CARD, UNCHANGED_FORM)

    emails = values(out, 'email')
    check('all 3 e-mails kept', len(emails) == 3, f"got {len(emails)}: {emails}")
    check('2nd e-mail intact', 'jean@home.example' in emails, emails)
    check('3rd e-mail intact', 'jean.dupont@old.example' in emails, emails)

    tels = values(out, 'tel')
    check('all 3 phone numbers kept', len(tels) == 3, f"got {len(tels)}: {tels}")

    types = [line.params.get('TYPE') for line in out.contents.get('email', [])]
    check('e-mail TYPE parameters kept', ['WORK'] in types and ['HOME'] in types, types)

    tel_types = [line.params.get('TYPE') for line in out.contents.get('tel', [])]
    check('phone TYPE parameters kept', ['CELL'] in tel_types and ['FAX'] in tel_types, tel_types)


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

    org = out.org.value
    check('ORG sub-units kept', org == ['Acme Corp', 'R&D', 'Team 4'], org)


def test_first_instance_is_the_one_edited():
    print("\nEditing a field changes the shown instance only")
    form = dict(UNCHANGED_FORM, EMAIL='jean.martin@acme.example')
    out = save(RICH_CARD, form)

    emails = values(out, 'email')
    check('edited e-mail applied', 'jean.martin@acme.example' in emails, emails)
    check('old first e-mail gone', 'jean@acme.example' not in emails, emails)
    check('other e-mails untouched', len(emails) == 3, f"got {len(emails)}: {emails}")


def test_clearing_a_field_removes_the_property():
    print("\nClearing a field removes that property")
    form = dict(UNCHANGED_FORM, NOTE='', URL='')
    out = save(RICH_CARD, form)

    check('NOTE removed', 'note' not in out.contents, out.contents.get('note'))
    check('URL removed', 'url' not in out.contents, out.contents.get('url'))
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


def test_photo_is_kept_and_typed_correctly():
    print("\nPhotos keep their bytes and get the right type")
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
    jpeg = b'\xff\xd8\xff' + b'\x00' * 40
    gif = b'GIF89a' + b'\x00' * 40
    webp = b'RIFF' + b'\x00\x00\x00\x00' + b'WEBP' + b'\x00' * 32

    check('JPEG detected', detect_image(jpeg) == ('JPEG', 'image/jpeg'), detect_image(jpeg))
    check('PNG detected', detect_image(png) == ('PNG', 'image/png'), detect_image(png))
    check('GIF detected', detect_image(gif) == ('GIF', 'image/gif'), detect_image(gif))
    check('WebP detected', detect_image(webp) == ('WEBP', 'image/webp'), detect_image(webp))
    check('not an image rejected', detect_image(b'not an image') is None, detect_image(b'not an image'))

    out = save(RICH_CARD, dict(UNCHANGED_FORM, PHOTO=png))
    check('PNG stored as TYPE=PNG', out.photo.params.get('TYPE') == ['PNG'], out.photo.params)
    check('photo bytes round-trip', out.photo.value == png, len(out.photo.value or b''))

    # An edit that does not touch the photo must leave it alone.
    kept = save(out.serialize(), UNCHANGED_FORM)
    check('photo kept when not re-uploaded', kept.photo.value == png, 'photo changed')


def test_rev_moves_forward():
    print("\nREV marks the card as changed")
    out = save(RICH_CARD, UNCHANGED_FORM)
    rev = values(out, 'rev')
    check('REV updated', rev and rev[0] != '20200101T120000Z', rev)
    check('REV looks like a timestamp', rev and rev[0].endswith('Z') and len(rev[0]) == 16, rev)


def test_new_card_is_valid():
    print("\nA new card is well formed")
    text = build_new_vcard({
        'FN': 'Ada Lovelace',
        'FIRST_NAME': 'Ada',
        'LAST_NAME': 'Lovelace',
        'EMAIL': 'ada@example.org',
        'TEL': '',
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
    check('empty fields left out', 'tel' not in out.contents, out.contents.get('tel'))
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
        'EMAIL': 'bob@example.org',
        'TEL': '', 'ORG': '', 'URL': '', 'BDAY': '', 'NOTE': '',
        'ADR': {'street': '', 'city': '', 'postal': '', 'country': ''},
    })
    check('FN updated', values(out, 'fn') == ['Bob Smith'], values(out, 'fn'))
    check('N created', out.n.value.family == 'Smith', str(out.n.value))
    check('e-mail added', values(out, 'email') == ['bob@example.org'], values(out, 'email'))
    check('no empty ADR added', 'adr' not in out.contents, out.contents.get('adr'))


def main():
    for test in [
        test_unshown_properties_survive,
        test_additional_emails_and_phones_survive,
        test_structured_components_survive,
        test_first_instance_is_the_one_edited,
        test_clearing_a_field_removes_the_property,
        test_special_characters_are_escaped,
        test_photo_is_kept_and_typed_correctly,
        test_rev_moves_forward,
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
