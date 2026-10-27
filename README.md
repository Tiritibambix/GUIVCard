<p align="center">
  <img src="static/media/guivcard-banner.png" alt="GUIVCard" width="100%">
</p>

<p align="center">
  <a href="https://hub.docker.com/r/tiritibambix/guivcard"><img src="https://img.shields.io/docker/pulls/tiritibambix/guivcard?logo=docker&logoColor=white&label=Docker%20Pulls&color=2496ED" alt="Docker Pulls"></a>
  <a href="https://hub.docker.com/r/tiritibambix/guivcard"><img src="https://img.shields.io/docker/image-size/tiritibambix/guivcard/latest?logo=docker&logoColor=white&label=Image%20Size&color=2496ED" alt="Docker Image Size"></a>
  <img src="https://img.shields.io/badge/Arch-amd64%20%7C%20arm64-informational?logo=linux&logoColor=white" alt="Architectures">
  <a href="https://github.com/Tiritibambix/GUIVCard/actions/workflows/docker-build.yml"><img src="https://github.com/Tiritibambix/GUIVCard/actions/workflows/docker-build.yml/badge.svg" alt="Build Status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue.svg" alt="License"></a>
</p>

---

> ⚠️ **Security notice**
>
> This application has been vibe coded and is designed for local or trusted-network use only. Exposing it to the public internet without an additional access-control layer (reverse proxy with auth, VPN, etc.) is done at your own risk.

---

## What is GUIVCard?

A clean, dark-themed web interface for managing contacts stored on a [Radicale](https://radicale.org) CardDAV server.

- **No database** — contacts live in Radicale, not in this app
- **No separate user accounts** — authentication is delegated entirely to Radicale
- **Multi-user ready** — each user accesses only their own address book
- **Self-hosted** — Docker image available for amd64 and arm64

---

## Features

### Authentication
- Login with your Radicale credentials (username + password)
- Authentication verified via `PROPFIND` against your CardDAV collection — no separate user store
- Multi-user: each user accesses only their own address book, isolated by URL (`{username}` placeholder)
- **Your password never reaches your browser.** It stays in the app's memory for the session; the browser holds only an opaque, `HttpOnly`, `SameSite=Strict` session cookie
- Sessions end after 12 hours idle, 7 days at most, on sign-out, or when the container restarts
- CSRF protection on all state-changing requests, with a fresh token on each sign-in

### Contact management
- **Create** contacts with first name, last name (optional), organization, website, birthday, address, notes, and photo
- **Several emails and phone numbers** per contact, each with a type (home, work, mobile, fax…)
- **Edit** contacts in a modal — existing photo preserved unless a new one is uploaded or explicitly removed
- **Delete** contacts with a confirmation dialog
- **Import and export** `.vcf` files. Export writes the cards exactly as the server stored them; import skips a card whose UID is already present rather than overwriting it
- **Nothing you can't see is lost.** Saving a contact keeps every property the editor doesn't show — `NICKNAME`, `TITLE`, `ROLE`, `IMPP`, `CATEGORIES`, custom `X-*` fields — and every `TYPE` parameter it doesn't manage, such as `PREF` and `INTERNET`. Structured values keep their hidden components too: `N` its prefix and middle name, `ADR` its post box and region, `ORG` its sub-units
- **No silent overwrites.** Every write carries `If-Match`, so a contact changed on your phone since the page loaded is reported as a conflict instead of being overwritten
- **Birthdays without a year** work in all three forms found in the wild: vCard's `--MMDD`, Apple's year 1604 with `X-APPLE-OMIT-YEAR`, and iOS cards that use 1604 without the marker. A card keeps the form it arrived in
- vCard 3.0, serialized with `vobject` for RFC-compliant escaping

### Photos
- **Metadata is stripped.** An uploaded photo is decoded and re-encoded, so the GPS coordinates of where it was taken, the camera model and the timestamp never reach your address book
- **Orientation is applied**, because Google Contacts ignores the EXIF flag and would show a portrait photo on its side
- **Size is bounded** to 1024 px and 512 KB, past what any client displays — a raw phone photo becomes megabytes of base64 that servers refuse and every device re-downloads on each sync
- Transparency is kept by storing as PNG; everything else becomes JPEG

### Browse & sort
- Live search across name, email, phone, organization, address fields — no page reload
- Sort by **first name**, **last name**, or **organization** — preference persisted across actions
- Empty fields pushed to the bottom on all sort modes
- Contact counter updates in real time while filtering

### UI
- Dark theme, custom CSS — no CDN dependency
- Avatar with initials fallback when no photo is available
- Flash messages colored by type: green for success, red for error
- Keyboard shortcuts: `/` focuses the search, `N` opens a new contact, `Esc` closes a dialog or clears the search, `?` lists them. A single key never fires while you are typing
- Accessibility: labels on every input, ARIA roles on dialogs, list semantics on the contact list, the result count announced as it changes, and the focus returned to whatever opened a dialog. This has **not** been audited with a screen reader or an automated checker — see [compatibility](docs/compatibility.md)

### Security headers
Every response carries a Content Security Policy with no `unsafe-inline` for
scripts — the one inline script block is allowed by a per-response nonce, and
the templates contain no inline event handler. Alongside it:
`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, a
`Permissions-Policy` denying camera, microphone, geolocation, payment and USB,
and HSTS when `SECURE_COOKIES` is on.

### Infrastructure
- Runs on **gunicorn** (production WSGI server) — no Flask dev server warning. One worker with 8 threads, since sessions live in the process's memory
- Multi-stage Docker image: the compiler toolchain stays in the build stage
- Docker image published on Docker Hub: `tiritibambix/guivcard`
- Multi-architecture builds: `linux/amd64`, `linux/arm64`
- Uploads are bounded by `MAX_CONTENT_LENGTH`, and a card the server refuses for its size reports why
- Dependency security audit via `pip-audit` on every push
- vCard round-trip tests gate the image build, so a save can never start dropping fields unnoticed
- GitHub Actions CI with explicit `GITHUB_TOKEN` permission scoping

---

## Requirements

- A running [Radicale](https://radicale.org) CardDAV server
- Docker (recommended) or Python 3.11+

---

## Quick start with Docker

**1. Create a `.env` file:**

```env
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
CARDDAV_URL=http://radicale:5232/{username}/contacts/
```

`{username}` is replaced at login time with the authenticated user's username.  
For a single-user setup, use a fixed URL: `http://radicale:5232/admin/contacts/`

**2. Run:**

```bash
docker compose up -d
```

**3. Open** `http://YOUR_SERVER_IP:8190` and sign in with your Radicale credentials.

---

## Environment variables

| Variable         | Required | Description                                                                                                  |
|------------------|----------|--------------------------------------------------------------------------------------------------------------|
| `SECRET_KEY`     | Yes      | Flask session signing key. Generate once and keep stable across restarts.                                    |
| `CARDDAV_URL`    | Yes      | CardDAV collection URL. Supports `{username}` placeholder for multi-user setups.                             |
| `SECURE_COOKIES` | No       | Set to `true` to mark the session cookie `Secure` and send HSTS. Turn it on behind an HTTPS reverse proxy; leave it off for the plain-HTTP quick start, or sign-in will not work. |

## Documentation

- [Compatibility](docs/compatibility.md) — which servers and clients have actually been checked, and the known gaps. Read this before trusting the app with an address book you care about.
- [Security policy](.github/SECURITY.md) — what is in scope and how to report a vulnerability privately.

---

## Docker Compose example

```yaml
services:
  app:
    image: tiritibambix/guivcard:latest
    ports:
      - "8190:5000"
    environment:
      # Flask secret key — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
      - SECRET_KEY=${SECRET_KEY}
      # CardDAV URL. Use {username} placeholder for multi-user setups:
      #   http://radicale:5232/{username}/contacts/
      # Or a fixed collection (single-user):
      #   http://radicale:5232/admin/contacts/
      - CARDDAV_URL=${CARDDAV_URL}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/login"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

---

## Local development

```bash
git clone https://github.com/Tiritibambix/GUIVCard.git
cd GUIVCard
pip install -r app/requirements.txt
export SECRET_KEY=dev CARDDAV_URL=http://localhost:5232/{username}/contacts/
python app/app.py
```

Run the vCard tests — they need no server and no test framework:

```bash
python tests/test_vcard_roundtrip.py
```

---

## Health check

The app exposes a `/health` endpoint that verifies connectivity to your CardDAV server.

Access it from the UI via the **Status** link in the navigation bar. It displays:
- CardDAV server URL
- HTTP status code returned by the server
- A success or error message

This is useful for diagnosing connection issues between GUIVCard and Radicale.

---

## CI / CD

| Workflow                  | Trigger                        | What it does                                                                    |
|---------------------------|--------------------------------|---------------------------------------------------------------------------------|
| `docker-build.yml`        | Push to `main`, PRs            | Audit deps, build `linux/amd64` + `linux/arm64`, push `:latest` + `:<sha>`     |
| `docker-build-test.yml`   | Manual (`workflow_dispatch`)   | Audit deps, build `linux/amd64` only, push `:test`                              |

---

## License

GPL-3.0 — see [LICENSE](LICENSE).
