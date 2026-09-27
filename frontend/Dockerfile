# Build static assets
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
# The image renders templates/*.template into conf.d/ at startup, filling in
# API_KEY so proxied /api calls carry the backend's X-API-Key.
ENV API_KEY=""     NGINX_ENVSUBST_FILTER="^API_KEY$"
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]