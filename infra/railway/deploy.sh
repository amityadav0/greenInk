#!/usr/bin/env bash
# Deploy Green Ink to Railway: Postgres, Redis, a storage bucket, and three services from one repo.
#
# Before the first run:
#   1. railway login
#   2. Have NEBIUS_API_KEY and TAVILY_API_KEY in .env at the repo root.
# Run from the repo root:  infra/railway/deploy.sh
# Re-running redeploys the code; setup steps that already exist are skipped.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROJECT="${PROJECT:-greenink}"
say() { printf '\n== %s\n' "$*"; }
env_value() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

railway whoami >/dev/null || { echo "Run 'railway login' first."; exit 1; }
for key in NEBIUS_API_KEY TAVILY_API_KEY; do
  [ -n "$(env_value "$key")" ] || { echo "$key is missing from .env"; exit 1; }
done

if ! railway status >/dev/null 2>&1; then
  say "Creating project $PROJECT"
  railway init --name "$PROJECT"
fi

services="$(railway status --json 2>/dev/null || true)"
has() { grep -q "\"name\": *\"$1\"" <<<"$services"; }

say "Databases"
has Postgres || railway add --database postgres
has Redis || railway add --database redis

say "Services"
for service in api worker web; do
  has "$service" || railway add --service "$service"
done

session_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
common=(
  "DATABASE_URL=\${{Postgres.DATABASE_URL}}"
  "REDIS_URL=\${{Redis.REDIS_URL}}"
  "NEBIUS_API_KEY=$(env_value NEBIUS_API_KEY)"
  "TAVILY_API_KEY=$(env_value TAVILY_API_KEY)"
  "ENV=production"
  "LOG_LEVEL=INFO"
  "RAILWAY_DOCKERFILE_PATH=infra/Dockerfile"
)
if [ -n "${BUCKET_ENDPOINT:-}" ]; then
  common+=(
    "R2_ENDPOINT_URL=$BUCKET_ENDPOINT"
    "R2_ACCESS_KEY_ID=$BUCKET_ACCESS_KEY_ID"
    "R2_SECRET_ACCESS_KEY=$BUCKET_SECRET_ACCESS_KEY"
    "R2_BUCKET=$BUCKET_NAME"
    "R2_ADDRESSING_STYLE=${BUCKET_ADDRESSING_STYLE:-virtual}"
  )
fi

say "Variables"
args=()
for kv in "${common[@]}"; do args+=(--set "$kv"); done
railway variables --service api --skip-deploys "${args[@]}" \
  --set "ROLE=api" --set "PORT=8000" --set "HOST=::" --set "MIGRATE_ON_START=1" \
  --set "SESSION_SECRET=${SESSION_SECRET:-$session_secret}"
railway variables --service worker --skip-deploys "${args[@]}" --set "ROLE=worker"
railway variables --service web --skip-deploys \
  --set "API_URL=http://\${{api.RAILWAY_PRIVATE_DOMAIN}}:8000" --set "PORT=3000"

say "Deploying api and worker (repo root, infra/Dockerfile)"
railway up --service api --detach
railway up --service worker --detach

say "Deploying web (apps/web)"
railway up apps/web --path-as-root --service web --detach

say "Public URL"
railway domain --service web --port 3000 || true
echo
echo "Watch: railway logs --service api   |   railway logs --service worker"
