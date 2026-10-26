# Green Ink

**Get to the green ink.** Green Ink finds Indian government (GeM) tenders a small manufacturer can actually win, then lists every clause that would get the bid rejected, with the page it sits on and the fix.

> Small factories don't lose government tenders on price. They lose on page 37.

Demo URL, video and screenshot: coming with the Oct 28 production deploy.

## Status

Foundations are in place, and the contracts are frozen (`contracts/openapi.yaml`, `greenink.core`). The pipeline, the product screens and the data adapters are being built now in three lanes (see `docs/SPEC.md`). Routes that aren't built yet return `501` with the standard error shape.

## Quickstart

Requires Docker, [uv](https://docs.astral.sh/uv/) and pnpm.

```bash
cp .env.example .env          # set NEBIUS_API_KEY and TAVILY_API_KEY
docker compose up --build     # postgres, redis, minio, api :8000, worker, web :3000
```

Developing outside Docker:

```bash
make install        # uv sync --all-packages + pnpm install
make lint test      # ruff, mypy, import-linter, contract checks, web typecheck, pytest
make check-models   # ping every configured Nemotron model on Token Factory
make gem-spike      # search GeM and download 10 bid PDFs to data/raw/
make openapi        # regenerate contracts and the web client types
```

## How we use NVIDIA Nemotron on Nebius Token Factory

Every model call goes through one gateway (`packages/greenink/llm`) to Nebius Token Factory's OpenAI-compatible API. Model IDs, fallbacks, prices and budgets live only in [`config/models.yaml`](config/models.yaml).

| Task | Model | Why |
| --- | --- | --- |
| Triage search results; company profile from a website | Nemotron 3.5 Lightning | Cheap and fast; runs on every search result |
| Extract requirements with page and verbatim quote | Nemotron 3 Super | Strong instruction-following on long documents |
| Scanned pages and BoQ tables with no text layer | Nemotron 3.5 Super VL | Vision, only where text extraction fails |
| Judge each requirement against the company; draft fixes | Nemotron 3 Ultra | The hardest reasoning step, once per report |

The verdict (Bid / Fix then bid / Skip) is computed by code from the findings, never by a model. A requirement reaches the report only if its quote is found on its cited page.

## Architecture

A modular monolith driven by queues: one codebase and one image, which runs as `api` or as `worker --queues …`. Domain modules in `packages/greenink/` talk only through typed ports, enforced by import-linter in CI. See [`docs/SPEC.md`](docs/SPEC.md).

```text
apps/api      FastAPI /v1, SSE progress, 202 + id for long work
apps/worker   arq workers: ingest, parse, extract, judge, intel, triage
apps/web      Next.js 15, Tailwind, react-pdf
packages/greenink/{core,sources,docs,llm,analysis,companies,intel,triage,storage,jobs,db}
contracts/    openapi.yaml + JSON Schemas (generated, frozen)
config/       models.yaml, sources.yaml
```

## Data sources and terms

- GeM bid listings and documents are public. We fetch them at 1 request a second with a user agent that names this project, cache them, and link every bid back to its official page.
- Tavily results are cited in the price panel.
- The demo company, Brightline Electricals, is fictional.

## Limitations

To be published with the evaluation (Oct 29): see `docs/PLAN.md`, "Evaluation and limitations".

## Licence

[MIT](LICENSE)
