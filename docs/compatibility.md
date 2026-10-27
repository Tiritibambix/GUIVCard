# Compatibility

What has actually been checked, and what has not. An entry without evidence is
a gap, not a claim — the point of this file is that the gaps stay visible.

Update it whenever something is verified, with the date and the versions used.

## CardDAV servers

| Server          | Evidence                                                        | Limits |
|-----------------|-----------------------------------------------------------------|--------|
| Radicale        | The target server throughout development; the app is written against its behaviour. No automated end-to-end suite runs against it. | No claim about every version or configuration. |
| Baïkal          | **Not verified.** Expected to work: the app speaks RFC 6352 and Baïkal is the other common choice. | Discovery for an installation under a path has not been tried. Baïkal can serve a stored 4.0 card as 3.0. |
| Xandikos        | **Not verified.** | |
| Nextcloud       | **Not verified.** | Group storage differs (`CATEGORIES` per contact rather than group cards), and GUIVCard does not handle groups at all yet. |

The address book must already exist on the server; GUIVCard does not create
collections. It authenticates with a CardDAV username and password only — no
SSO, no delegated authentication.

## Synced clients

GUIVCard edits the contacts your other devices sync, so what those devices
write matters as much as what the server stores.

| Client                      | Evidence |
|-----------------------------|----------|
| DAVx⁵ on Android            | **Not verified on a device.** Cards in its style are covered by the vCard tests below. |
| Apple Contacts / iOS        | **Not verified on a device.** The year-less birthday convention it uses (year 1604 with `X-APPLE-OMIT-YEAR`) is handled and covered by the vCard tests. |
| Thunderbird                 | **Not verified.** |
| Google Contacts             | **Not verified on a device.** It ignores a photo's EXIF orientation, which is why uploads are straightened before being stored. |

## What the vCard tests do cover

`tests/test_vcard_roundtrip.py` runs on every push and gates the image build.
It asserts, against a synthetic card carrying the kind of content Apple and
DAVx⁵ write:

- Properties the editor does not show survive a save: additional e-mails and
  phone numbers, their `TYPE` parameters, `NICKNAME`, `TITLE`, `ROLE`, `IMPP`,
  `CATEGORIES` and `X-*` extensions.
- Structured values keep the components the editor does not expose: `N` keeps
  its prefix, suffix and middle name; `ADR` keeps its post box, extended
  address and region; `ORG` keeps its sub-units.
- Clearing a field removes the property; editing one changes only the instance
  the UI displayed.
- Semicolons and commas in text values are escaped rather than breaking the
  field structure.
- Birthdays without a year round-trip in all three forms found in the wild.
- An uploaded photo is re-encoded, straightened and bounded, and its metadata
  is gone.

These are unit-level checks against the parser and serializer. **They do not
prove anything about a real server or a real phone.**

## Known gaps

- **One address book per user.** The collection is fixed by `CARDDAV_URL`;
  there is no discovery and no way to switch or move a contact between books.
- **No groups.** Group cards are not read or written. `CATEGORIES` is shown in
  the detail view, but read-only: a contact's existing group membership is
  preserved on save and now visible, yet there is no way to change it here.
- **One language.** English only.
- **No photo cropping.** An uploaded photo is scaled to fit, never cropped.
- **The detail view is read-only beyond the editor's fields.** Everything a
  card holds is shown, but only what the editor has an input for can be
  changed. The rest is preserved, not editable.
- **No focus trap in dialogs.** Focus is moved into a dialog when it opens and
  given back when it closes, but `Tab` can still reach the page behind it.
- **Import skips rather than merges.** A card whose UID is already present is
  left alone; there is no conflict resolution for a bulk import.

## Browsers

Developed against current Chrome and Firefox. The app uses no framework and no
CDN; it does rely on `<template>`, `replaceChildren`, `closest` and optional
JSON parsing of data attributes, so a browser older than roughly 2021 will not
work. **Not verified on Safari.**
