#!/bin/sh
set -eu
PORT="${PORT:-${ERGANI_UI_PORT:-8080}}"
exec uv run --group ui gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  "ui.app:app"
