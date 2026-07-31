#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/opt/intranet-dges"
BACKUP_DIR="/opt/intranet-dges-backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

cd "$BASE_DIR"
mkdir -p "$BACKUP_DIR/$TIMESTAMP"

set -a
source .env
set +a

echo "Sauvegarde PostgreSQL..."
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$BACKUP_DIR/$TIMESTAMP/postgres.sql"

echo "Sauvegarde des documents..."
if [ -d media ]; then
  tar -czf "$BACKUP_DIR/$TIMESTAMP/media.tar.gz" media
fi

echo "Sauvegarde terminee dans $BACKUP_DIR/$TIMESTAMP"

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
