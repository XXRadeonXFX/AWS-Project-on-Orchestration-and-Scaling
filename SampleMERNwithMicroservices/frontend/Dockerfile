# Build stage
FROM node:18-alpine as build

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY package*.json ./
RUN npm install

# Copy entire frontend code
COPY . .

# Build the React app
RUN npm run build

# --------------------------

# Production stage using nginx
FROM nginx:alpine

# Copy build files to nginx html directory
COPY --from=build /app/build /usr/share/nginx/html

# Expose default nginx port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
