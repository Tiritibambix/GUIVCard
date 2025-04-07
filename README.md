# GuiVCard

A modern CardDAV client with web interface.

## Tech Stack

- Backend: Python + Flask
- Frontend: React + TypeScript
- CardDAV Client: carddav (Python)
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

Copy the docker-compose.yml file and adjust the environment variables according to your needs:

```yaml
version: '3.8'

services:
  backend:
    image: tiritibambix/guivcard-backend:latest
    ports:
      - "8191:5000"
    environment:
      - CARDDAV_URL=http://radicale:5232/contacts.vcf
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD_HASH=your_hashed_password
      - CORS_ORIGIN=http://localhost:8190

  frontend:
    image: tiritibambix/guivcard-frontend:latest
    ports:
      - "8190:80"
    environment:
      - REACT_APP_API_URL=http://localhost:8191
```

Then start the containers:

```bash
docker-compose up -d
```

### Environment Variables

#### Backend
- `CARDDAV_URL`: Your CardDAV server URL
- `ADMIN_USERNAME`: Admin username for authentication
- `ADMIN_PASSWORD_HASH`: Hashed password for admin (use werkzeug.security.generate_password_hash)
- `CORS_ORIGIN`: Frontend URL (default: http://localhost:8190)

#### Frontend
- `REACT_APP_API_URL`: Backend API URL (default: http://localhost:8191)

## Ports

The application uses the following ports:
- Backend API: 8191
- Frontend UI: 8190

Access the application at http://your-server:8190

## Security

- All API endpoints require authentication
- Passwords are hashed and never stored in plain text
- CORS is configured for secure cross-origin requests
- All configuration is done through Docker environment variables

## Development

The source code is available on GitHub. The project uses GitHub Actions for CI/CD:
- Automatic building of Docker images
- Security audit of dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub updates