<p align="center">
  <img src="static/media/guivcard-banner.png" alt="GUIVCard" width="100%">
</p>

---

> ⚠️ **Security notice**
>
> This application has been vibe coded and is designed for local or trusted-network use only. Exposing it to the public internet without an additional access-control layer (reverse proxy with auth, VPN, etc.) is done at your own risk.

---

# GUIVCard

A clean, dark-themed web interface for managing contacts stored on a [Radicale](https://radicale.org) CardDAV server. No database, no user accounts — authentication is delegated entirely to Radicale.

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

## Requirements

- A running [Radicale](https://radicale.org) CardDAV server
- Docker (recommended) or Python 3.11+

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

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing key. Generate once and keep stable across restarts. |
| `CARDDAV_URL` | Yes | CardDAV collection URL. Supports `{username}` placeholder for multi-user setups. |

## Docker Compose example

```yaml
services:
  app:
    image: tiritibambix/guivcard:latest
    ports:
      - "8190:5000"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - CARDDAV_URL=${CARDDAV_URL}
    restart: unless-stopped
```

## Local development

```bash
git clone https://github.com/Tiritibambix/GUIVCard.git
cd GUIVCard
pip install -r app/requirements.txt
export SECRET_KEY=dev CARDDAV_URL=http://localhost:5232/{username}/contacts/
python app/app.py
```

## CI / CD

| Workflow | Trigger | What it does |
|---|---|---|
| `docker-build.yml` | Push to `main` | Audit deps, build `linux/amd64` + `linux/arm64`, push `:latest` + `:<sha>` |
| `docker-build-test.yml` | Manual (`workflow_dispatch`) | Audit deps, build `linux/amd64` only, push `:test` |

## License

GPL-3.0 — see [LICENSE](LICENSE).
