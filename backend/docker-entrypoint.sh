#!/bin/sh
# Docker-only entrypoint: the committed database/schema.prisma defaults to SQLite for
# zero-config local dev (see docs/database.md); in the container we switch it to
# PostgreSQL (docker-compose provisions a real Postgres instance) before generating the
# client and syncing the schema. This edits the schema file INSIDE the container's
# filesystem only — it never touches your host checkout.
set -e

echo "Switching database/schema.prisma to the postgresql provider for this container..."
sed -i 's/provider = "sqlite"/provider = "postgresql"/' ../database/schema.prisma

echo "Generating Prisma client..."
npx prisma generate --schema=../database/schema.prisma

echo "Syncing database schema..."
npx prisma db push --schema=../database/schema.prisma --accept-data-loss --skip-generate

echo "Seeding (safe to re-run — upserts the admin user, only seeds demo cameras if none exist)..."
npx tsx prisma/seed.ts

echo "Starting backend..."
exec node dist/index.js
