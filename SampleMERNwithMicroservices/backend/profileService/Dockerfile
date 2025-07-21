FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm installRUN npm install
COPY . .
EXPOSE 3002
CMD ["npm", "index.js"]
