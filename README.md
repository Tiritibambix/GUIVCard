# GuiVCard

A CardDAV client with web interface.

## Tech Stack
- Python + Flask
- CardDAV Client: caldav
- Authentication: Basic auth
- UI: Tailwind CSS
- Deployment: Docker
- Deployment: Docker

## Docker Image

Pre-built Docker image is available on Docker Hub:
`tiritibambix/guivcard`

Image is built automatically for amd64 architecture.

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
  - CARDDAV_URL=https://your.carddav-server.com/username/contacts/
  - ADMIN_USERNAME=your_username
  - ADMIN_PASSWORD=your_password
```

Replace:
- `your.carddav-server.com/username/contacts/` with the full URL to your CardDAV address book
  - For Radicale, it's typically `https://radicale.example.com/username/contacts/`
  - You can find this URL in your Radicale web interface
- `your_username` with your CardDAV username
- `your_password` with your CardDAV password
- `YOUR_SERVER_IP` with your server's IP address or domain name

### Run the Application

```bash
docker-compose up -d
```

## Port

The application runs on port 8190.

Access the application at http://YOUR_SERVER_IP:8190

## Authentication

The application uses Basic Auth with the credentials configured in docker-compose.yml to authenticate with the CardDAV server.

## Security Notes

- Never commit passwords or sensitive information to the repository
- Use HTTPS in production
- Keep your modified docker-compose.yml secure and never commit it

## Development

The source code is available on GitHub. The project uses GitHub Actions for CI/CD:
- Automatic building of Docker images
- Security audit of dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub updates