#!/bin/sh
# One image, three roles. The first argument picks the role; the rest pass through.
#   api                     FastAPI on $PORT (default 8000)
#   worker [--queues all]   queue worker
#   migrate                 alembic upgrade head
set -eu

role="${1:-api}"
[ "$#" -gt 0 ] && shift

case "$role" in
  api)
    exec uvicorn greenink_api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers "$@"
    ;;
  worker)
    [ "$#" -eq 0 ] && set -- --queues=all
    exec greenink-worker "$@"
    ;;
  migrate)
    exec alembic -c packages/greenink/db/alembic.ini upgrade head
    ;;
  *)
    echo "unknown role: $role (expected api, worker or migrate)" >&2
    exit 64
    ;;
esac
