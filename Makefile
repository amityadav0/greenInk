# Green Ink developer commands. Python via uv, web via pnpm, services via docker compose.
.DEFAULT_GOAL := help
SHELL := /bin/bash

UV_RUN := uv run $(if $(wildcard .env),--env-file .env,)
WEB := pnpm --dir apps/web
ALEMBIC := uv run alembic -c packages/greenink/db/alembic.ini

.PHONY: help install dev down test lint fmt openapi migrate seed check-models gem-spike run-one eval

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install Python (all workspace packages) and web dependencies
	uv sync --all-packages
	$(WEB) install --frozen-lockfile

dev: ## Run the whole stack: postgres, redis, minio, api, worker, web
	docker compose up --build

down: ## Stop the stack
	docker compose down

test: ## Run the Python tests (DB tests need `docker compose up postgres`, else they skip)
	uv run pytest

lint: ## ruff, mypy, import-linter, contract freshness, web typecheck
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run lint-imports
	uv run python scripts/export_contracts.py --check
	$(WEB) typecheck

fmt: ## Format and autofix Python
	uv run ruff format .
	uv run ruff check --fix .

openapi: ## Regenerate contracts/openapi.yaml, contracts/schemas/ and the web client types
	uv run python scripts/export_contracts.py
	$(WEB) gen:api

migrate: ## Apply migrations to DATABASE_URL
	$(UV_RUN) $(ALEMBIC) upgrade head

seed: ## Load the fictional Brightline Electricals demo company
	$(UV_RUN) python scripts/seed.py

check-models: ## Ping every model in config/models.yaml on Token Factory (needs NEBIUS_API_KEY)
	$(UV_RUN) python scripts/check_models.py

gem-spike: ## Search GeM and download 10 bid PDFs to data/raw (Q="current transformer")
	uv run python scripts/gem_spike.py "$(or $(Q),current transformer)"

run-one: ## Cited report for one bid: make run-one BID=GEM-2026-B-8175711 [ARGS="--fixes 2"]
	$(UV_RUN) python scripts/run_one.py "$(BID)" $(ARGS)

eval: ## Run the evaluation set (writes eval/results.csv)
	$(UV_RUN) python eval/run.py
