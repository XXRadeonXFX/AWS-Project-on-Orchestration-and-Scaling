# Use a minimal Node.js base image
FROM node:18-alpine

# Set the working directory
WORKDIR /app

# Copy only necessary files first (for better Docker caching)
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 3000

# Start the app
CMD ["npm", "start"]
