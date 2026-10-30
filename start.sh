#!/bin/sh
# Start script for hosting (Railway, Docker, or any server).
# Needs DATABASE_URL and SECRET_KEY. Set SUPERADMIN_USERNAME and SUPERADMIN_PASSWORD to create the Super Admin on first start.
set -e
cd "$(dirname "$0")/backend"

python -m alembic upgrade head

if [ -n "$SUPERADMIN_PASSWORD" ]; then
  python create_superadmin.py || true
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8001}" --proxy-headers --forwarded-allow-ips="*"
