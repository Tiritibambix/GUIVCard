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
- Backend: `yourusername/guivcard-backend`
- Frontend: `yourusername/guivcard-frontend`

Images are built automatically for both amd64 and arm64 architectures.

## Project Structure

```
├── backend/           # Python Flask backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── config/
├── frontend/         # React frontend
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   └── public/
├── docker/          # Docker related files
│   └── nginx/
├── docker-compose.yml
└── README.md
```

## Features

- Simple authentication
- CardDAV integration (GET/PUT/POST on .vcf)
- Contact management (list, create, edit, delete)
- Modern responsive UI

## Deployment

All configuration is done through the docker-compose.yml file. Modify the environment variables in the docker-compose.yml file according to your needs:

```yaml
# Backend environment variables
CARDDAV_URL: Your CardDAV server URL
ADMIN_USERNAME: Admin username for authentication
ADMIN_PASSWORD_HASH: Hashed password for admin (use werkzeug.security.generate_password_hash)
CORS_ORIGIN: Frontend URL (default: http://localhost:8190)

# Frontend environment variables
REACT_APP_API_URL: Backend API URL (default: http://localhost:8191)
```

Example docker-compose.yml:

```yaml
services:
  backend:
    image: yourusername/guivcard-backend:latest
    ports:
      - "8191:5000"
    environment:
      - CARDDAV_URL=http://radicale:5232/contacts.vcf
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD_HASH=your_hashed_password
      - CORS_ORIGIN=http://localhost:8190

  frontend:
    image: yourusername/guivcard-frontend:latest
    ports:
      - "8190:80"
    environment:
      - REACT_APP_API_URL=http://localhost:8191
```

To deploy:

```bash
docker-compose up -d
```

## Ports

The application uses the following ports:
- Backend API: 8191
- Frontend UI: 8190

Access the application at http://your-server:8190

## Development

### Local Development

This is a Docker-based application intended to be run in containers. The development environment is fully containerized to ensure consistency across different environments.

### CI/CD

The project uses GitHub Actions for continuous integration and deployment:
- Automatic building of Docker images for both frontend and backend
- Security audit of Python and Node.js dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub description updates
- Versioned Docker images using Git commit hashes

## Security

- All API endpoints require authentication
- Passwords are hashed and never stored in plain text
- CORS is configured for secure cross-origin requests
- All configuration is done through Docker environment variables
- Regular security audits through CI/CD pipeline