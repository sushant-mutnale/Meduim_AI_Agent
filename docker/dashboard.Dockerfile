FROM node:20-alpine

WORKDIR /app

# Copy package files (assumes they exist after 'npx create-next-app')
COPY package.json package-lock.json* ./
RUN npm install

# Copy application source code
COPY . .

# Expose port and start
EXPOSE 3000
CMD ["npm", "run", "dev"]
