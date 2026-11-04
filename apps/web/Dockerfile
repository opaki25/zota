FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY apps/web apps/web
ENV API_URL=http://api:8000
RUN npm run build
USER node
EXPOSE 3000
CMD ["npm", "run", "start", "-w", "apps/web"]
