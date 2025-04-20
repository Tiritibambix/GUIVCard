<p align="center">
  <img src="static/media/guivcard-banner.png" alt="GuiVCard Banner" width="400">
</p>

# GuiVCard

GuiVCard is a web application designed to manage contacts via a CardDAV server. It provides an intuitive user interface and advanced features for seamless contact management.

## Features

- **Secure Authentication**: Login with username and password.
- **Contact Management**:
  - Add, update, and delete contacts.
  - Display detailed contact information.
  - Dynamic search among contacts.
- **CardDAV Integration**:
  - Retrieve and manage contacts from a CardDAV server.
  - Generate and update vCards.
- **Modern User Interface**:
  - Design powered by Tailwind CSS.
  - Responsive layout for all devices.
  - Scrollable interface for long content.

## Prerequisites

- Python 3.8 or higher
- A functional CardDAV server
- Dependencies listed in `requirements.txt`

## Installation

### Local Installation (Python)

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/GUIVCard.git
   cd GUIVCard
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   - `CARDDAV_URL`: URL of your CardDAV server
   - `ADMIN_USERNAME`: Admin username
   - `ADMIN_PASSWORD`: Admin password

4. Run the application:
   ```bash
   python app/app.py
   ```

### Docker Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/GUIVCard.git
   cd GUIVCard
   ```

2. Run the application using Docker Compose:
   ```bash
   docker-compose up -d
   ```

## Usage

The application runs on port 8190.

Access the application at:  
`http://YOUR_SERVER_IP:8190`

## Deployment

### Configuration

The application uses Basic Auth with credentials configured in `docker-compose.yml` to authenticate with the CardDAV server.

### Security Notes

- Never commit passwords or sensitive information to the repository.
- Use HTTPS in production.
- Keep your modified `docker-compose.yml` secure and never commit it.

## Development

The source code is available on GitHub. The project uses GitHub Actions for CI/CD:
- Automatic building of Docker images
- Security audit of dependencies
- Multi-architecture support (amd64, arm64)
- Automatic Docker Hub updates
