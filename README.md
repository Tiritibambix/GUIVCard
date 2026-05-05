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
- CSRF protection on all state-changing requests
- Flask session secured with a configurable `SECRET_KEY`

### Contact management
- **Create** contacts with first name, last name (optional), organization, email, phone, website, birthday, address, notes, and photo
- **Edit** contacts in a modal — existing photo preserved unless a new one is uploaded
- **Delete** contacts with a confirmation dialog
- vCard 3.0 generation with proper RFC-compliant escaping

### Browse & sort
- Live search across name, email, phone, organization, address fields — no page reload
- Sort by **first name**, **last name**, or **organization** — preference persisted across actions
- Empty fields pushed to the bottom on all sort modes
- Contact counter updates in real time while filtering

### UI
- Dark theme, custom CSS — no CDN dependency
- Avatar with initials fallback when no photo is available
- Flash messages colored by type: green for success, red for error
- Fully accessible: labels on all inputs, ARIA roles on dialogs, keyboard navigation (Escape closes modals)

### Infrastructure
- Runs on **gunicorn** (production WSGI server) — no Flask dev server warning
- Docker image published on Docker Hub: `tiritibambix/guivcard`
- Multi-architecture builds: `linux/amd64`, `linux/arm64`
- Dependency security audit via `pip-audit` on every push
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

| Variable       | Required | Description                                                                               |
|----------------|----------|-------------------------------------------------------------------------------------------|
| `SECRET_KEY`   | Yes      | Flask session signing key. Generate once and keep stable across restarts.                 |
| `CARDDAV_URL`  | Yes      | CardDAV collection URL. Supports `{username}` placeholder for multi-user setups.          |

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
