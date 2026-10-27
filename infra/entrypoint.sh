#!/bin/sh
# One image, three roles. The role is the first argument, else $ROLE, else api.
#   api                     FastAPI on $PORT (default 8000); runs `migrate` first if MIGRATE_ON_START=1
#   worker [--queues all]   queue worker
#   migrate                 alembic upgrade head, then seed the demo company
set -eu

# Platforms that override the command may repeat our own name (e.g. "entrypoint api").
[ "${1:-}" = "entrypoint" ] && shift
role="${1:-${ROLE:-api}}"
[ "$#" -gt 0 ] && shift

migrate() {
  alembic -c packages/greenink/db/alembic.ini upgrade head
  python -c "import asyncio; from greenink.core.settings import get_settings; from greenink.db.session import make_engine, make_sessionmaker; from greenink.db.seed import seed_demo; asyncio.run(seed_demo(make_sessionmaker(make_engine(get_settings().database_url))))"
}

case "$role" in
  api)
    [ "${MIGRATE_ON_START:-0}" = "1" ] && migrate
    # HOST=:: on Railway, whose private network is IPv6-only (asyncio binds "::" as IPv6-only).
    exec uvicorn greenink_api.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' "$@"
    ;;
  worker)
    [ "$#" -eq 0 ] && set -- --queues=all
    exec greenink-worker "$@"
    ;;
  migrate)
    migrate
    ;;
  *)
    echo "unknown role: $role (expected api, worker or migrate)" >&2
    exit 64
    ;;
esac
