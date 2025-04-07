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

### Generate Password Hash

Before deploying, generate a password hash for authentication:

```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_password'))"
```

This will output something like:
```
pbkdf2:sha256:600000$randomsalt$hashedpassword
```

Copy this hash and use it in your docker-compose.yml for the ADMIN_PASSWORD_HASH environment variable.

### Configuration

Copy and adjust the docker-compose.yml for your environment:

```yaml
services:
  backend:
    image: tiritibambix/guivcard-backend:latest
    ports:
      - "8191:5000"
    environment:
      - CARDDAV_URL=http://radicale:5232/contacts.vcf
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD_HASH=your_generated_hash
      - CORS_ORIGIN=http://your-server:8190

  frontend:
    image: tiritibambix/guivcard-frontend:latest
    ports:
      - "8190:80"
    environment:
      - REACT_APP_API_URL=http://your-server:8191
```

Replace:
- `your_generated_hash` with the hash generated above
- `your-server` with your server's IP or domain name

### Start the Application

```bash
docker-compose up -d
```

## Ports

The application uses the following ports:
- Backend API: 8191
- Frontend UI: 8190

Access the application at http://your-server:8190

## Security

- All API endpoints require authentication
- Passwords are hashed using Werkzeug's secure hash algorithm
- CORS is configured for secure cross-origin requests
- All configuration is done through Docker environment variables

## Development

The source code is available on GitHub. The project uses GitHub Actions for CI/CD:
- Automatic building of Docker images
- Security audit of dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub updates