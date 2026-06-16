"""Unified FastAPI layer.

Serves two feature sets from one server:
  * ESG research assistant — chat sessions, streaming agent, reports (app.agent / app.chat_history)
  * ESG Evidence Engine — precomputed scoring/signal/witness JSON + live news (backend.engine / backend.data)

Run from the repo root so the absolute ``backend.*`` engine imports resolve:
    uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.engine import config
from backend.engine.pipeline import build

from .agent import (
    AssistantRequest,
    AssistantResponse,
    ChatMessage,
    OpenRouterAgent,
    ToolResult,
    collect_company_esg_news,
)
from .chat_history import (
    ChatHistoryStore,
    ChatSessionDetail,
    ChatSessionSummary,
    CreateChatSessionRequest,
)


class Product(BaseModel):
    name: str
    value: int
    change: str


class Portfolio(BaseModel):
    customer_count: int
    transaction_volume: int
    risk_score: int
    uptime: str
    products: list[Product]


app = FastAPI(title="PolyFintech 2026 API", version="1.0.0")
agent = OpenRouterAgent()
chat_history = ChatHistoryStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Agent rate limit — the site is public, so a global per-day cap on AI messages
# bounds API cost (the dashboard and all data stay unrestricted). Persisted to a
# gitignored file so the cap survives restarts.
# --------------------------------------------------------------------------- #
AGENT_DAILY_LIMIT = int(os.environ.get("AGENT_DAILY_LIMIT", "100"))
_RATE_FILE = Path(__file__).resolve().parents[2] / "cache" / "agent" / "agent_rate.json"


def _agent_rate_allow() -> bool:
    """Count one agent message against today's global cap. Returns False once the
    daily limit is reached, so the costly LLM call is skipped."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        data = json.loads(_RATE_FILE.read_text("utf-8")) if _RATE_FILE.exists() else {}
    except Exception:
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    if int(data.get("count", 0)) >= AGENT_DAILY_LIMIT:
        return False
    data["count"] = int(data.get("count", 0)) + 1
    try:
        _RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RATE_FILE.write_text(json.dumps(data), "utf-8")
    except Exception:
        pass
    return True


def _rate_limited_response() -> AssistantResponse:
    note = (
        f"The shared daily limit of {AGENT_DAILY_LIMIT} AI messages has been "
        "reached. The dashboard and all data are still fully available — please "
        "try the assistant again tomorrow."
    )
    return AssistantResponse(
        message=ChatMessage(role="assistant", content=note),
        tool_results=[
            ToolResult(name="rate_limit", status="error", summary=note, source_count=0)
        ],
        model=agent.model,
    )


# --------------------------------------------------------------------------- #
# ESG Evidence Engine — build precomputed JSON on startup, then serve it.
# --------------------------------------------------------------------------- #
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
    return {"status": "ok", "service": "polyfintech-esg"}


@app.get("/api/portfolio", response_model=Portfolio)
def portfolio() -> Portfolio:
    return Portfolio(
        customer_count=12840,
        transaction_volume=4280000,
        risk_score=18,
        uptime="99.98%",
        products=[
            Product(name="Digital Wallets", value=1820000, change="+18.4%"),
            Product(name="SME Lending", value=1410000, change="+11.2%"),
            Product(name="Cross-border Pay", value=1050000, change="+9.7%"),
        ],
    )


@app.get("/api/companies")
def companies():
    return _read("companies.json")


@app.get("/api/matrix")
def matrix():
    return _read("matrix.json")


@app.get("/api/signals")
def signals():
    return _read("signals.json")


@app.get("/api/regulations")
def regulations():
    """Catalog of tracked SG/ASEAN ESG regimes: who each binds + demo-set status counts."""
    return _read("regulations.json")


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


@app.get("/api/esg-news/company")
async def company_esg_news(
    company: str,
    ticker: str | None = None,
    domain: str | None = None,
    max_results: int = 8,
):
    """Live company-specific ESG/news evidence for any company in the UI universe."""
    result = await collect_company_esg_news(
        web_tools=agent.web_tools,
        company=company,
        ticker=ticker,
        domain=domain,
        max_results=max_results,
    )
    return {
        "company": company,
        "ticker": ticker,
        "domain": domain,
        "queries": result["queries"],
        "errors": result["errors"],
        "sources": [
            source.model_dump(by_alias=True) for source in result["sources"]
        ],
        "referenceArticles": [
            article.model_dump(by_alias=True)
            for article in result["reference_articles"]
        ],
    }


# --------------------------------------------------------------------------- #
# ESG research assistant — chat sessions + streaming agent.
# --------------------------------------------------------------------------- #
@app.get("/api/assistant/sessions", response_model=list[ChatSessionSummary])
def assistant_sessions() -> list[ChatSessionSummary]:
    return chat_history.list_sessions()


@app.post("/api/assistant/sessions", response_model=ChatSessionSummary)
def create_assistant_session(
    request: CreateChatSessionRequest,
) -> ChatSessionSummary:
    return chat_history.create_session(title=request.title)


@app.get("/api/assistant/sessions/{session_id}", response_model=ChatSessionDetail)
def assistant_session(session_id: str) -> ChatSessionDetail:
    try:
        return chat_history.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Chat session not found.") from exc


@app.delete("/api/assistant/sessions/{session_id}", status_code=204)
def delete_assistant_session(session_id: str) -> Response:
    if not chat_history.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return Response(status_code=204)


@app.post("/api/assistant/chat", response_model=AssistantResponse)
async def assistant_chat(request: AssistantRequest) -> AssistantResponse:
    if not _agent_rate_allow():
        return _rate_limited_response()
    session = chat_history.ensure_session(request.session_id)
    effective_request = request.model_copy(update={"session_id": session.id})
    persist_latest_user_message(session.id, request)
    response = await agent.run(effective_request)
    chat_history.append_assistant_response(
        session.id,
        response,
        request.page_context,
    )
    return response


@app.post("/api/assistant/chat/stream")
async def assistant_chat_stream(request: AssistantRequest) -> StreamingResponse:
    if not _agent_rate_allow():
        async def limited():
            yield json.dumps(
                {"type": "final", "response": _rate_limited_response().model_dump(by_alias=True)},
                ensure_ascii=False,
            ) + "\n"

        return StreamingResponse(limited(), media_type="application/x-ndjson")
    session = chat_history.ensure_session(request.session_id)
    effective_request = request.model_copy(update={"session_id": session.id})
    persist_latest_user_message(session.id, request)

    async def events():
        async for event in agent.stream(effective_request):
            if event.get("type") == "final" and event.get("response"):
                response = AssistantResponse(**event["response"])
                chat_history.append_assistant_response(
                    session.id,
                    response,
                    request.page_context,
                )
                event["session"] = chat_history.get_session_summary(
                    session.id,
                ).model_dump(by_alias=True)
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


def persist_latest_user_message(session_id: str, request: AssistantRequest) -> None:
    for message in reversed(request.messages):
        if message.role == "user":
            chat_history.append_user_message(
                session_id,
                message.content,
                request.page_context,
            )
            return
