# PolyFintech 2026

React + FastAPI ESG evidence and agent workspace for Singapore-listed companies.

## Structure

- `frontend/` - Vite, React, TypeScript, Tailwind CSS
- `backend/` - FastAPI app with typed API responses

## Run Locally

Install frontend dependencies:

```bash
cd frontend
npm install
npm run dev
```

Install backend dependencies and run from the **repo root** (the engine uses
absolute `backend.*` imports):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

On first start the ESG Evidence Engine seeds its database and precomputes the
dashboard JSON offline (no network required); subsequent starts reuse it.

Open the frontend at `http://localhost:5173`.

The frontend proxies `/api/*` requests to `http://localhost:8000`.

## Features

- **AI Assistant** — chat sessions, streaming research agent, source-backed PDF reports (`/api/assistant/*`).
- **ESG Evidence Engine** — scoring/signal/witness/forecast over a Singapore universe, served as `/api/companies`, `/api/matrix`, `/api/signals`, `/api/company/{id}`, and live `/api/news`. UI lives under the "Evidence Engine" and "Live News" sidebar sections.

## Scraper providers

All credentials are environment-only. Configure any combination and enable it from Settings:

```env
BRIGHTDATA_API_KEY=
BRIGHTDATA_API_KEY_FALLBACK=
SCRAPEDO_API_TOKEN=
OXYLABS_USERNAME=
OXYLABS_PASSWORD=
SEARXNG_BASE_URL=
CRAWL4AI_BASE_URL=
```

The pipeline fans out across enabled providers, canonicalizes URLs, groups duplicate claims, and stops after repeated discovery rounds yield no new evidence. It does not bypass login pages, authentication, or hard paywalls.

Start the free self-hosted stack locally with:

```bash
docker compose -f docker-compose.scrapers.yml up -d
```

Then set `SEARXNG_BASE_URL=http://localhost:8080` and `CRAWL4AI_BASE_URL=http://localhost:11235`.

For Railway, create two private services from this repository with root directories `infra/searxng` and `infra/crawl4ai`. Set `SEARXNG_SECRET` on the SearXNG service, then configure the main app with the Railway private-network URLs. These scraper services do not need public domains.

## Research controls

Settings provides Daily, Weekly (Monday), or Monthly (first day) scheduling at 06:00 Singapore time, provider and source-type selection, a full-universe Run now action, and manual review of source-promotion candidates. Raw extracted pages expire after 30 days; grouped claims and provenance remain in SQLite.

The deployed app is installable from `/app` using the browser's Add to Home Screen action.

## Data provenance (real vs. seeded)

This is a prototype, so the data is a deliberate mix of genuinely-sourced and
illustrative-seeded inputs. We keep this explicit rather than implying every
number is live.

**Real (genuinely sourced):**

- **Latest-year (2023) claims & evidence** — extracted by LLM directly from each
  company's actual sustainability-report PDF, then independently corroborated via
  web search (claims become `VERIFIED` only when a credible third-party source
  confirms them; otherwise `ASSERTED`; undisclosed material topics are filled by
  labelled `INFERRED` estimates).
- **Stock prices + STI benchmark** — real weekly OHLC scraped via Bright Data
  (Yahoo Finance, with native/MarketWatch fallbacks).
- **Live News** — real headlines scraped weekly via Bright Data SERP, then each
  headline is classified (controversy / positive / stock / neutral, or dropped as
  irrelevant) by an LLM, with a deterministic keyword classifier as the no-key
  fallback. The resulting sentiment is a real leading feature in the forecaster.
- **Company universe** (names, tickers, sectors, SASB industries) and the
  **regulation definitions** (SGX-711B, SGX Climate, IFRS S2/ISSB, MAS-ENRM,
  ASEAN Taxonomy) are real reference data.

**Seeded (illustrative — not live):**

- **Rater scores** (MSCI / S&P / Sustainalytics) and the derived consensus,
  divergence, and Trust Meter. These are commercial, paywalled products with no
  reliable free source, so they are hand-authored to illustrate rating spread.
- **Compliance statuses** (MET / PARTIAL / MISSING per regulation). The
  regulations themselves are real; each company's status is illustrative (no
  public ground-truth dataset exists).
- **Witness event pins** (CDP emissions-verified markers, controversy markers)
  on the 2019–2023 Price Witness chart, and the **pre-2023 evidence trajectory**.
  Real news is current-dated and cannot be placed on the fixed historical
  backtest window.
- **Fundamentals** (P/E, dividend yield) used as forecast inputs.

**Credential fallback.** Live extraction/verification/scraping require
`OPENROUTER_API_KEY` and Bright Data keys in a git-ignored `.env`. When those are
absent, every live path degrades gracefully to the seeded snapshot committed in
the repo (`backend/data/esg.db`, `backend/out/`, `backend/cache/`) — the app runs
fully offline with no network and no keys.

