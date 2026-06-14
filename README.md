# ESG Evidence Engine

> *Don't measure ESG. Find what the market mispriced.*

An interactive dashboard that scores **Singapore-listed companies** by **verifying their claims
against evidence**, surfaces **rater disagreement** as a trust signal, and flags **Underpriced
Improvers** — verified ESG improvement the market has not yet priced. **Every number traces back
to a source sentence.**

Built for the CGS International ESG hackathon. The thesis (from the brief): the alpha is not in
ESG *leaders* but in ESG *improvers* — companies the market still rates on what they *were*, not
what they are *becoming*.

---

## The idea in one screen

- **ESG Momentum Matrix** — where the market rates a company *today* (rater consensus) × where the
  *evidence* is heading (verified-evidence momentum). The opportunity lives in **Hidden Winners**:
  low score today, improving fast.
- **Underpriced Improver** = `proof_up` (verified evidence rising) **and** `opinion_flat` (raters
  stale or disagreeing) **and** `price_flat` (the stock hasn't reacted vs the STI). All three legs,
  or it doesn't flag.
- **Price Witness** — weekly candles under a rising verified-evidence band: *the gap you can see*.
  A witness, not an oracle — it shows non-reaction, it never predicts returns.
- **Trust Meter** — divergence across MSCI / Sustainalytics / S&P (normalised, Sustainalytics
  inverted). High divergence = low trust.
- **Compliance gap** — SGX / ISSB / MAS / ASEAN-Taxonomy disclosure status, effective-year gated.
- **ESG forecast** — an *explainable* next-year prediction from **leading** alt-data signals (never
  the lagged score), labelled **HYPOTHESIS** with feature attribution.

Every score, flag and pin has a **“why?”** drill-down that resolves to the source sentence (or, for
the forecast, its feature contributions).

---

## Run locally (one command each)

**Backend** (the engine + API; auto-seeds the DB and precomputes everything offline on first run):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
# run from the repo root so `backend` is importable:
cd ..
uvicorn backend.app.main:app --port 8000
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The frontend proxies `/api/*` to `http://localhost:8000`.

### Demo-day / offline mode (zero network)

The pipeline runs entirely from the local SQLite DB + claim cache + saved model:

```bash
python -m backend.engine.pipeline --offline      # rebuild backend/out/*.json, no network/LLM
```

`--offline` is enforced by test **T4**. The live LLM path (OpenAI, set `OPENAI_API_KEY`) is only
used to (re)extract claims; results are cached, so the demo never depends on a live call.

---

## Data: Bright Data → Excel → SQLite

- **SQLite (`backend/data/esg.db`) is the source of truth.** Bright Data scrapes into an Excel/CSV
  workbook whose sheet names match the table names; `import_excel.py` loads it 1:1:
  ```bash
  python -m backend.data.import_excel path/to/bright_data.xlsx     # import a scraped workbook
  python -m backend.data.import_excel --export sample.xlsx         # export the current DB
  python -m backend.data.seed                                      # rebuild the deterministic seed DB
  ```
- The schema (every table + column) is documented in [`backend/data/schema.md`](backend/data/schema.md).
- **Seed data is illustrative** (deterministic, Singapore-first, clearly synthetic) so the demo
  works without scraping. The **engine logic is identical** on real Bright Data / `yfinance` inputs —
  real data drops in with no engine change.
- **Missing data is `null` / “N.A.”, never fabricated** (enforced by test **T7**). Caches live in
  `backend/cache/`; precomputed JSON in `backend/out/`; the trained model in `backend/models/`.

### Live Bright Data scraping

Credentials go in `backend/.env` (git-ignored — see `backend/.env.example`):
`BRIGHTDATA_API_KEY` + `BRIGHTDATA_ZONE` (Web Unlocker) **or** `BRIGHTDATA_PROXY` (a Scraping
Browser zone is used over CDP). Everything routes through `engine/brightdata.py` with a mandatory
**cache + STALE fallback** — a failed scrape never crashes the pipeline.

```bash
python -m backend.data.scrape --check     # validate credentials with one request
python -m backend.data.scrape --news      # live news/controversy per company (Bing News) -> out/news.json
```

`--news` pulls real, current headlines via the **Bright Data Scraping Browser** and surfaces them
as a **Live news signal** panel on each company page (clearly marked as current, outside the
2019–2023 evidence window). Robots-restricted sources (e.g. Yahoo prices) are skipped by design.

---

## Architecture / module map

```
Bright Data ─► data/import_excel.py ─► data/esg.db (SQLite)
                                          │
              backend/engine (standalone, UI-independent, unit-tested)
  ingest → claims(LLM) → sasb → verify(3-state) → score(per-year, trace)
         → normalize → divergence → regulations(compliance) → signal
         → witness(band/pins/flat) → predict(ML, HYPOTHESIS)
                                          │
               pipeline.py → backend/out/*.json → FastAPI → React dashboard
```

| Module | Responsibility |
|---|---|
| `engine/ingest.py`, `engine/db.py` | Read SQLite → typed models |
| `engine/claims.py`, `engine/llm.py` | LLM claim extraction (OpenAI or mock) + verbatim-source guard |
| `engine/sasb.py` | Map claims to material SASB topics (weights in `config/sasb_materiality.json`) |
| `engine/verify.py` | 3-state verification (VERIFIED / ASSERTED; ABSENT is topic-level) |
| `engine/score.py` | Per-year evidence score (absence lowers confidence, not the score) |
| `engine/normalize.py`, `engine/divergence.py` | Rater percentiles (invert Sustainalytics) + Trust Meter |
| `engine/regulations.py` | Compliance gap, effective-year gated |
| `engine/signal.py` | Underpriced Improver + quadrant |
| `engine/witness.py` | Price Witness (candles, band, pins, STI-relative flat) |
| `engine/predict.py` | Explainable Ridge forecaster (leading features only) |
| `app/main.py` | FastAPI serving the precomputed JSON |
| `frontend/src/components/{dashboard,company}` | Screener, Momentum Matrix, company detail, Price Witness, trace drill-down |

---

## Tests (the definition of done)

```bash
cd <repo root>
backend/.venv/Scripts/python -m pytest backend/tests/ -q     # 15 passed
```

| Test | Guarantees |
|---|---|
| **T1** | every score/flag/signal traces to a non-empty source sentence (forecast → feature attribution) |
| **T2** | after normalisation all three raters rank a strong name above a weak one (catches a forgotten Sustainalytics flip) |
| **T3** | absence isolation — extra ABSENT topics leave the score unchanged, only confidence drops |
| **T4** | `--offline` runs the full pipeline with **zero** network calls |
| **T5** | `is_underpriced_improver` is true **iff** all three legs are true |
| **T6** | normalisation is purely rank-based (rescaling a rater doesn't move percentiles) |
| **T7** | no fabrication — missing data is `null`, no default-fills in the pipeline |
| **T8** | the forecast is explainable, reports its test error, is HYPOTHESIS-labelled, and never uses the lagged score |
| **T9** | compliance never penalises a not-yet-in-force regulation or an unknown status |

---

## HYPOTHESIS vs verified

- **Verified** (traces to evidence): evidence scores, claim states, rater divergence, compliance status.
- **HYPOTHESIS** (not backtested on this set, labelled in the UI): the ESG forecast, and the claim
  that Underpriced Improvers / the Price Witness gap translate into future returns. The Price Witness
  shows *non-reaction*; it does not assert causation, and carries no technical indicators.

## Sources & fallbacks

| Layer | Source (production) | Seed / fallback |
|---|---|---|
| Prices | Bright Data market data | `yfinance` (`<code>.SI`, `^STI`), else synthetic weekly walk |
| Rater scores | MSCI / Sustainalytics / S&P public pages | seed workbook (`null` where uncovered) |
| Reports / claims | Company sustainability reports (Bright Data PDF) | seed `documents` table + cached extraction |
| Evidence | CDP, regulator/penalty records, news, job boards | seed `evidence` / `events` |
| Regulations | SGX / ISSB / MAS / ASEAN Taxonomy | `config/regulations.json` |
