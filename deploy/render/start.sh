#!/bin/sh
set -eu

: "${PORT:?Render must provide PORT}"
test -f /app/frontend/dist/index.html
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --no-proxy-headers
