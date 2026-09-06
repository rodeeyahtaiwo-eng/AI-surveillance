# Build context is the repo root (see docker/docker-compose.yml) so this image can
# include ../database/schema.prisma alongside backend/, mirroring the host layout.
FROM node:20-alpine

# Prisma's query engine needs OpenSSL on Alpine.
RUN apk add --no-cache openssl

WORKDIR /app

COPY database ./database
COPY backend ./backend
WORKDIR /app/backend

RUN npm install
RUN npm run build
RUN chmod +x docker-entrypoint.sh

EXPOSE 4000
ENTRYPOINT ["./docker-entrypoint.sh"]
