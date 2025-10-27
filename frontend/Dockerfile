# Build static assets
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Dist is expected to be served by your reverse proxy (e.g., Caddy).
# If you want a standalone container serving static files, you can add an nginx/alpine stage here.