# Data schema — `esg.db` (SQLite, source of truth)

Bright Data scrapes into an Excel/CSV workbook whose **sheet names match these table
names**; `import_excel.py` loads it 1:1. Missing cells stay **NULL** — never default-filled (T7).

| Table | Key | Columns | Notes |
|---|---|---|---|
| `universe` | company_id | ticker, name, country, exchange, sector, sasb_industry, scope | `scope ∈ {demo, reference}` — demo = the 10 rendered SG names; reference = ASEAN panel for ranking/ML only |
| `rater_scores` | company_id, year | msci_letter, sustainalytics_risk, sp_global | Sustainalytics is **risk (lower=better)** — inverted in `normalize.py`. NULL allowed |
| `prices` | company_id, week_date | open, high, low, close, volume | **Weekly Fridays only.** STI benchmark stored under reserved `company_id = "_STI"` |
| `fundamentals` | company_id, period | pe, dividend_yield | |
| `documents` | doc_id | company_id, title, year, url, source_page, text | `text` is the report excerpt the LLM extracts claims from |
| `evidence` | evidence_id | company_id, domain, authority_source, snippet, url, supports, date, topic_id | `domain ∈ {climate, governance, supply_chain, labour}`; `supports=1` corroborates, `0` contradicts |
| `events` | (company_id, date) | type, label, value | `type ∈ {emissions_verified, hiring_surge, rater_unchanged, controversy}` → Price-Witness pins |
| `regulations` | reg_id | jurisdiction, name, scope, requirement, effective_year | SGX/ISSB/MAS/ASEAN regimes; `effective_year` gates applicability |
| `reg_compliance` | company_id, reg_id, year | status, evidence_ref | `status ∈ {MET, PARTIAL, MISSING, NA}`; NULL = unknown (never MISSING) |

## Bundled config (in `engine/config/`, versioned — not in the DB)
- `sasb_materiality.json` — industry → material topics + **weights (sum=1.0)**. The only place weights live.
- `source_authority.json` — domain → authoritative/specialist sources for verification.
- `regulations.json` — seed of the regulatory regimes (also loaded into the `regulations` table).

## Rebuild / import
```
python -m backend.data.seed                       # rebuild the deterministic demo DB
python -m backend.data.import_excel data.xlsx     # import a Bright Data workbook
python -m backend.data.import_excel --export out.xlsx   # export current DB to Excel
```
