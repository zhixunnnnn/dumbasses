"""FastAPI layer — serves the precomputed ESG Evidence Engine JSON to the dashboard.

UI-independent engine -> JSON in backend/out/ -> these endpoints. On startup, if the
output is missing it is built offline (zero network), so `uvicorn app.main:app` just works.
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.engine import config
from backend.engine.pipeline import build

app = FastAPI(title="ESG Evidence Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _ensure_built() -> None:
    # one-command run: seed the DB if empty, then precompute the dashboard JSON (offline).
    from backend.engine import ingest

    if not ingest.load().companies:
        from backend.data.seed import build as seed_build
        seed_build()
    if not (config.OUT_DIR / "companies.json").exists():
        build(offline=True)


def _read(rel: str):
    path = config.OUT_DIR / rel
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{rel} not found — run the pipeline")
    return json.loads(path.read_text("utf-8"))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "esg-evidence-engine"}


@app.get("/api/companies")
def companies():
    return _read("companies.json")


@app.get("/api/matrix")
def matrix():
    return _read("matrix.json")


@app.get("/api/signals")
def signals():
    return _read("signals.json")


@app.get("/api/company/{company_id}")
def company(company_id: str):
    return _read(f"company/{company_id}.json")


@app.get("/api/news")
def news():
    """Live news/controversy scraped via Bright Data (empty until `scrape --news` runs)."""
    path = config.OUT_DIR / "news.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else {"companies": []}
