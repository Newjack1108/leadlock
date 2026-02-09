#!/bin/sh
set -e
port="${PORT:-3000}"
echo "Starting Next.js on 0.0.0.0:${port}..." >&2
exec node /app/node_modules/next/dist/bin/next start -H 0.0.0.0 -p "$port"
