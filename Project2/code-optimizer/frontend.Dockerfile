# 1) build stage
FROM node:20-alpine AS build
WORKDIR /app

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm ci --silent

# Copy the rest of the frontend code
COPY frontend/ .

# Build the app
RUN npm run build

# 2) runtime stage
FROM nginx:1.25-alpine

# Copy the built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config as template
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template

# Install bash for the entrypoint script
RUN apk add --no-cache bash

# Copy and make the entrypoint script executable
COPY frontend/docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

# Default backend URL (this will be overridden at runtime)
ENV BACKEND_URL=http://localhost:8000

EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]