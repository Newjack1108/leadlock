#!/bin/sh
# Run Next.js server; use node so we don't rely on PATH/npx in container.
set -e
port="${PORT:-3000}"
exec node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "$port"
