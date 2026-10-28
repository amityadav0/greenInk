# One image for every Python role; the command picks api, worker or migrate.
#   docker build -f infra/Dockerfile -t greenink .
#   docker run greenink [api | worker --queues all | migrate]   (or set ROLE)

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN uv sync --frozen --no-dev --all-packages --no-install-workspace --no-cache
COPY packages packages
COPY apps/api/greenink_api apps/api/greenink_api
COPY apps/worker/greenink_worker apps/worker/greenink_worker
RUN uv sync --frozen --no-dev --all-packages --no-cache

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home-dir /app greenink
WORKDIR /app
# Workspace packages are installed editable, so the source stays at the same path.
COPY --from=build /app/.venv .venv
COPY --from=build /app/packages packages
COPY --from=build /app/apps apps
COPY config config
COPY seed seed
COPY infra/entrypoint.sh /usr/local/bin/entrypoint
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 CONFIG_DIR=/app/config ENV=production
USER greenink
EXPOSE 8000
ENTRYPOINT ["entrypoint"]
# No CMD: the role comes from the first argument or $ROLE (api by default).
