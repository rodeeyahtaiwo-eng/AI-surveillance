# Build context is the repo root (see docker/docker-compose.yml).
FROM node:20-alpine AS builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend ./
# NEXT_PUBLIC_* vars must be present at build time — docker-compose passes them as
# build args so the compiled JS bundle points at the right backend URL.
ARG NEXT_PUBLIC_API_URL=http://localhost:4000/api
ARG NEXT_PUBLIC_WS_URL=ws://localhost:4000/ws
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
RUN npm run build

FROM node:20-alpine
WORKDIR /app/frontend
ENV NODE_ENV=production
COPY --from=builder /app/frontend ./
EXPOSE 3000
CMD ["npm", "start"]
