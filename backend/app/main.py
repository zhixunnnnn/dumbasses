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
    _start_weekly_scheduler()


def _start_weekly_scheduler() -> None:
    """Refresh Bright Data signals every Monday; catch up on startup if >7 days stale.
    Both run in background threads so they never block the server (or crash it)."""
    import threading

    from backend.data.weekly import run_weekly

    threading.Thread(target=run_weekly, daemon=True).start()  # startup catch-up (no-op if fresh)
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(lambda: run_weekly(force=True), CronTrigger(day_of_week="mon", hour=6))
        sched.start()
        print("Weekly Bright Data refresh scheduled (Mondays 06:00).")
    except Exception as exc:  # noqa: BLE001
        print(f"Weekly scheduler not started ({type(exc).__name__}); run `python -m backend.data.weekly`.")


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
    """Live news/controversy scraped via Bright Data, served from the DB (durable)."""
    from backend.engine.db import bootstrap
    from backend.data.scrape import load_news

    conn = bootstrap()
    try:
        return load_news(conn)
    finally:
        conn.close()
