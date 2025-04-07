# Build stage
FROM node:18-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy project files
COPY . .

# Create production env file
RUN echo "VITE_API_URL=${VITE_API_URL:-http://localhost:8195}" > .env.production

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Add nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Add script to replace environment variables
RUN echo $'\
#!/bin/sh\n\
envsubst < /usr/share/nginx/html/env-config.js.template > /usr/share/nginx/html/env-config.js\n\
exec nginx -g "daemon off;"\
' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Create template for runtime environment variables
RUN echo "window.ENV = { VITE_API_URL: '$VITE_API_URL' };" > /usr/share/nginx/html/env-config.js.template

EXPOSE 80

CMD ["/docker-entrypoint.sh"]