# Green Ink

**Get to the green ink.** Green Ink finds Indian government (GeM) tenders a small manufacturer can actually win, then lists every clause that would get the bid rejected, with the page it sits on and the fix.

> Small factories don't lose government tenders on price. They lose on page 37.

Demo URL, video and screenshot: coming with the Oct 28 production deploy.

## What it does

1. **Search** any product. Green Ink pulls live GeM bids and Nemotron 3.5 Lightning ranks each one green, amber or red for your company.
2. **Open a bid.** Green Ink downloads the bid and its linked attachments, reads every page (Nemotron 3.5 Super VL reads scanned ones), and Nemotron 3 Super lists every requirement with its page and a verbatim quote.
3. **Verify.** Code checks each quote against its cited page and drops any that don't match.
4. **Judge.** Nemotron 3 Ultra checks each verified requirement against the company profile. Code then computes the verdict (Bid / Fix then bid / Skip) from the findings.
5. **Fix and price.** Ultra drafts a fix for any gap. Tavily finds past prices, Lightning picks out the unit prices, and the price panel cites every source.

Every page citation opens the PDF at that page with the quote highlighted. The Model Trace shows each model call with its tokens, cost and latency. A second open of the same report is instant, served from cache.

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

## Deploy (Railway)

```bash
railway login
infra/railway/deploy.sh          # Postgres, Redis, api, worker, web; prints the public URL
```

GeM accepts only Indian IPs, so GeM traffic goes through a small relay on Vercel's Mumbai region (`infra/gem-relay`); set `GEM_RELAY_URL` and `GEM_RELAY_KEY` on the api and worker. The script reads the API keys from `.env`. For document storage, create a bucket in the Railway project canvas, then re-run with `BUCKET_ENDPOINT`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY` and `BUCKET_NAME` set. The web app proxies `/v1` to the API over Railway's private network.

## Data sources and terms

- GeM bid listings and documents are public. We fetch them at 1 request a second with a user agent that names this project, cache them, and link every bid back to its official page.
- Tavily results are cited in the price panel.
- The demo company, Brightline Electricals, is fictional.

## Limitations

- Only GeM is searched live; other portals work by upload. GeM's full-text search is loose, so many results are unrelated; triage marks them red.
- Scanned pages depend on vision accuracy; tables with merged cells can be misread.
- Hindi-only text is not read; quotes come from the English text of bilingual pages.
- A profile built from a website is marked unverified; the report is only as good as the profile.
- Price intel covers only publicly findable prices; with fewer than two unit prices, no band is shown.
- Advisory only: it does not replace reading the tender, and it never submits a bid.

The evaluation numbers follow on Oct 29 (`make eval`).

## Licence

[MIT](LICENSE)
