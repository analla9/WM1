# Stage 1: Build the React application
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the built application with Nginx
FROM nginx:1.25-alpine

# Copy built assets from the builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Remove default Nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx configuration (will be created in a later step,
# but the Dockerfile needs to reference it here)
# For now, Nginx will use its default behavior if this file isn't present at build time,
# or we can add a simple one here and overwrite it with a volume mount in docker-compose.
# Let's assume a custom nginx.conf will be copied or mounted for serving React app correctly.
# COPY nginx.conf /etc/nginx/conf.d/default.conf
# The actual nginx config for serving react will be handled by the main nginx service for the whole platform.
# This nginx in the frontend service is primarily to serve its static files.
# The main platform NGINX will proxy to this one or directly to the api-gateway.

# Expose port 80 (Nginx default)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
