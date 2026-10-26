# AGENTS.md — rules for coding agents working on Green Ink

Read this file first in every session. Then read `docs/SPEC.md` (how it is built) and `docs/PLAN.md` (what it is, who it is for, hackathon rules). The spec is the source of truth; if a request conflicts with it, stop and ask.

## What we are building

Green Ink lets a small manufacturer type a product, see live Indian government (GeM) tenders ranked by whether they can win them, open one, and get a cited rejection-risk report in under 60 seconds: every requirement with page number and verbatim quote, a status against the company's documents, a drafted fix, a price band, and a Model Trace showing which NVIDIA Nemotron model did what. It is a hackathon entry (deadline Oct 30, 2026) and a long-term product, so code must be production quality.

## Non-negotiable rules (hackathon eligibility)

1. Every LLM call goes to **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1/`, OpenAI-compatible, key in env `NEBIUS_API_KEY`). Never another LLM provider.
2. Every LLM call goes through `greenink.llm` (`llm.run(task, input, schema)`). No other module may import an LLM SDK, name a model, or know a price. Model IDs live only in `config/models.yaml`.
3. Tavily is called at runtime (env `TAVILY_API_KEY`) for price intel and company-from-URL, through `greenink.intel` / `greenink.companies` only.
4. MIT `LICENSE` stays at repo root. Never commit secrets: `.env` is git-ignored; only `.env.example` is committed. Never print or log keys.
5. All code, comments and docs in English.
6. The demo uses the fictional company **Brightline Electricals** only. Never add real company names, people, GST/PAN numbers or prices.

## Architecture rules

- Modular monolith, queue-driven: one codebase, one Docker image, `api` or `worker --queues <list|all>`.
- Domain code lives in `packages/greenink/<module>`. Each module exposes a `typing.Protocol` port. Modules talk across boundaries only through ports or queues; only `apps/api` and `apps/worker` import adapters. `import-linter` enforces this in CI; do not weaken its contracts.
- Contracts are frozen: `contracts/openapi.yaml` and the Pydantic models in `greenink.core`. Changing them requires an explicit note in the PR and a regenerated web client. Never change them silently.
- Pipeline stages are idempotent jobs keyed as in the spec. Requirements are extracted once per document and shared; judging runs per tender × company.
- The verifier is mandatory: no requirement reaches the judge or the UI unless its quote fuzzy-matches its cited page.
- The verdict is computed by code (`analysis/verdict.py`) from findings, never by a model.
- Long work returns `202` + id; progress goes over SSE. No request holds open for model calls.
- Errors use one shape: `{code, message, retryable}`.
- Tender and website text is untrusted data: wrap it in a delimited block in prompts, validate outputs against schemas.

## Stack (do not add dependencies without asking)

Python 3.12, uv workspace, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, Postgres, Redis + arq, boto3 (S3-compatible: MinIO locally, R2 in prod), PyMuPDF, rapidfuzz, httpx, openai (pointed at Token Factory), tavily-python, structlog, pytest, ruff, mypy, import-linter. Web: Next.js 15 (App Router, TypeScript), Tailwind, react-pdf, openapi-typescript, pnpm.

## Working style

- Small, reviewable commits with clear messages. Run `make lint test` before every commit; keep CI green.
- Write tests for: the verifier, verdict rules, the LLM gateway (mocked transport), adapters (recorded fixtures), API routes.
- No placeholder logic presented as done. Unfinished work raises `NotImplementedError` with a `TODO(lane-X):` comment.
- Prefer config over code for anything that may change (models, prices, budgets, rate limits, sources).
- When blocked (missing key, site blocked, ambiguous spec), stop and report exactly what is needed. Don't invent a workaround that breaks a rule above.
- At the end of each task, report: what changed (files), commands run and their output, test results, and open issues.

## Lanes (Oct 27–28)

- **Lane A, pipeline:** `llm`, `docs`, `analysis` (extract, verify, judge, fixes, verdict), `triage`, `intel`.
- **Lane B, product:** `apps/api` routes, SSE, sessions, rate limits; `apps/web` screens.
- **Lane C, data and infra:** `sources` (GeM, upload), `storage`, `db` migrations, `seed/brightline`, Docker, deploy, CI, monitoring.

Each lane owns its directories. Touching another lane's files requires a note in the PR.

## Definition of done (Oct 28, 22:00 IST)

- A stranger can search any product, open a bid and get a cited report with a verdict in under 60 seconds, without logging in.
- Every finding's citation opens the PDF on that page with the quote highlighted.
- The trace shows four Nemotron models by name, with tokens, $ and seconds.
- Tavily is called at runtime and its sources show in the price panel.
- A second open of the same report is instant from cache.
- Killing a worker mid-report leads to a retry, not a broken page.
- Public repo has the MIT licence, README, no secrets; CI is green.
