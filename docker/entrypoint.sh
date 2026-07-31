#!/bin/sh
set -e

echo "Attente de PostgreSQL sur ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
until nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
  sleep 1
done

echo "Application des migrations..."
python manage.py migrate --noinput

echo "Collecte des fichiers statiques..."
python manage.py collectstatic --noinput

exec gunicorn intranet_dges.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120
