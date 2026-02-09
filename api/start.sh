#!/bin/sh
# Run from repo root (path api/start.sh) or from api dir (path start.sh).
# Ensures we're in the api directory with venv, then start uvicorn.
set -e
if [ -d api ]; then
  cd api
fi
. venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
