#!/bin/sh
# Run from repo root (path api/start.sh) or from api dir (path start.sh).
# Ensures we're in the api directory, activates venv if it exists, then start uvicorn.
set -e
if [ -d api ]; then
  cd api
fi
if [ -f venv/bin/activate ]; then
  . venv/bin/activate
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
else
  exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
