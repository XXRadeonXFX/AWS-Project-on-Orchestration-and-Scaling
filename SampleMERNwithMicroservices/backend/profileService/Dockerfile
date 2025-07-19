# Use lightweight Node.js image
FROM node:18-alpine

# Set working directory inside the container
WORKDIR /app

# Copy package.json files and install only dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the code
COPY . .

# Expose the port used by the service
EXPOSE 3002

# Run the app
CMD ["npm", "start"]
