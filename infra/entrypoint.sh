#!/bin/sh
# One image, three roles. The first argument picks the role; the rest pass through.
#   api                     FastAPI on $PORT (default 8000)
#   worker [--queues all]   queue worker
#   migrate                 alembic upgrade head, then seed the demo company
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
    alembic -c packages/greenink/db/alembic.ini upgrade head
    exec python -c "import asyncio; from greenink.core.settings import get_settings; from greenink.db.session import make_engine, make_sessionmaker; from greenink.db.seed import seed_demo; asyncio.run(seed_demo(make_sessionmaker(make_engine(get_settings().database_url))))"
    ;;
  *)
    echo "unknown role: $role (expected api, worker or migrate)" >&2
    exit 64
    ;;
esac
