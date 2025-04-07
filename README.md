# GuiVCard

A modern CardDAV client with web interface.

## Tech Stack

- Backend: Python + Flask
- Frontend: React + TypeScript
- CardDAV Client: caldav (Python)
- Authentication: Basic auth
- UI: Tailwind CSS
- Deployment: Docker

## Docker Images

Pre-built Docker images are available on Docker Hub:
- Backend: `tiritibambix/guivcard-backend`
- Frontend: `tiritibambix/guivcard-frontend`

Images are built automatically for both amd64 and arm64 architectures.

## Features

- Simple authentication
- CardDAV integration (GET/PUT/POST on .vcf)
- Contact management (list, create, edit, delete)
- Modern responsive UI

## Deployment

### Configuration

Edit the docker-compose.yml file and replace the placeholders:

```yaml
environment:
  - CARDDAV_URL=https://your.carddav-server.com/admin/contacts/
  - ADMIN_USERNAME=your_username
  - ADMIN_PASSWORD=your_password
  - CORS_ORIGIN=http://YOUR_SERVER_IP:8190
```

Replace:
- `your.carddav-server.com/admin/contacts/` with the full URL to your CardDAV address book
  - For Radicale, it's typically `https://radicale.example.com/username/contacts/`
  - You can find this URL in your Radicale web interface
- `your_username` with your CardDAV username
- `your_password` with your CardDAV password
- `YOUR_SERVER_IP` with your server's IP address or domain name

### Run the Application

```bash
docker-compose up -d
```

## Ports

The application uses the following ports:
- Backend API: 8195
- Frontend UI: 8190

Access the application at http://YOUR_SERVER_IP:8190

## Authentication

The application uses a simple authentication flow:
1. Frontend authenticates with backend using Basic Auth
2. Backend uses the same credentials to authenticate with the CardDAV server
3. All credentials are configured in docker-compose.yml

## Security Notes

- Never commit passwords or sensitive information to the repository
- Use HTTPS in production
- Keep your modified docker-compose.yml secure and never commit it
- The backend acts as a secure proxy between the frontend and CardDAV server

## Development

The source code is available on GitHub. The project uses GitHub Actions for CI/CD:
- Automatic building of Docker images
- Security audit of dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub updates