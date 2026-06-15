# PolyFintech 2026

React + FastAPI starter for a fintech operations dashboard.

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
- **Live News** — real headlines scraped weekly via Bright Data SERP.
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

