"""Monday-morning manager briefing.

An LLM-synthesized digest of live news + verified-evidence signals for every
company the Evidence Dashboard covers, cached once per Asia/Singapore
calendar day so the dashboard loads instantly after the first request each
day (see backend/app/main.py: GET /api/dashboard/briefing).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .db import bootstrap
from .llm import OpenRouterLLMClient

SG_TZ = ZoneInfo("Asia/Singapore")
log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(SG_TZ).strftime("%Y-%m-%d")


def _all_company_ids() -> list[str]:
    path = config.OUT_DIR / "companies.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text("utf-8"))
    return [row["id"] for row in rows if row.get("id")]


def _load_company_json(company_id: str) -> dict | None:
    path = config.OUT_DIR / "company" / f"{company_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text("utf-8"))


def _load_news(conn, company_id: str) -> dict | None:
    row = conn.execute(
        "SELECT fetched_at, n_items, controversy, positive, sentiment "
        "FROM news WHERE company_id=?",
        (company_id,),
    ).fetchone()
    if not row:
        return None
    headlines = conn.execute(
        "SELECT title, url, label FROM news_headlines WHERE company_id=? "
        "ORDER BY fetched_at DESC LIMIT 8",
        (company_id,),
    ).fetchall()
    return {**dict(row), "headlines": [dict(h) for h in headlines]}


def _brief_input(company_id: str, conn) -> dict | None:
    payload = _load_company_json(company_id)
    if not payload:
        return None
    core = payload.get("company", {})
    evidence = payload.get("evidence", {})
    raters = payload.get("raters", {})
    signal = payload.get("signal", {})
    return {
        "id": company_id,
        "name": core.get("name") or company_id,
        "ticker": core.get("ticker"),
        "sector": core.get("sector"),
        "evidenceScore": evidence.get("total"),
        "pillars": evidence.get("pillars"),
        "confidence": evidence.get("confidence"),
        "raterConsensus": raters.get("consensus"),
        "raterDivergence": raters.get("divergence"),
        "quadrant": signal.get("quadrant"),
        "isUnderpricedImprover": signal.get("is_underpriced_improver"),
        "evidenceGap": signal.get("evidence_gap"),
        "momentum": signal.get("momentum"),
        "news": _load_news(conn, company_id),
    }


PROMPT_TEMPLATE = """You are writing the Monday-morning ESG briefing for a portfolio/CGS-I \
manager who has about 60 seconds before their first meeting. Below is this week's data for \
every company on the desk's evidence-scoring dashboard (evidenceScore = verified-evidence \
score 0-100, raterConsensus = mean percentile of MSCI/S&P/Sustainalytics, raterDivergence = \
how much the raters disagree, quadrant = UNDERPRICED_IMPROVER / OVERRATED / HIDDEN_WINNERS / \
etc., news.headlines = recent scraped ESG/controversy headlines with a label of \
stock/positive/neutral).

Write (a) ONE portfolio-level overview across the whole desk, and (b) a per-company briefing. \
Be specific and use the numbers given — do not invent facts not present in the data. If news is \
null or headlines are empty, say so plainly rather than fabricating events.

The overview is what the manager reads first and may be the ONLY thing they read: lead with the \
single most consequential thing across the desk this week, name the specific companies that \
drive it, and quantify where you can (how many are overrated, where controversies landed, which \
way momentum is going).

Return strict JSON: {{
"overview": {{
  "headline": "<one sentence, <=120 chars: the week across the whole desk>",
  "summary": "<3-5 sentences: the cross-company picture — concentrations of risk, notable moves, what it means for positioning. Name specific companies.>",
  "watch_items": ["<short phrase: desk-level thing to watch this week>", "... 2-4 items"]
}},
"companies": [{{
  "id": "<company id, must match input>",
  "headline": "<one punchy sentence, <=110 chars, the single most important thing this week>",
  "summary": "<2-4 sentences: what changed and why it matters, referencing the actual numbers/headlines given>",
  "potential_effects": ["<short phrase: a concrete downstream effect on price/rating/compliance risk>", "... 2-4 items"],
  "watch_items": ["<short phrase: what to watch for next>", "... 1-3 items"],
  "sentiment": "<positive|neutral|negative|mixed>"
}}]}}

COMPANIES:
{companies_json}
"""


def get_or_generate_briefings(
    company_ids: list[str] | None = None, refresh: bool = False
) -> dict:
    ids = [c for c in dict.fromkeys(company_ids or _all_company_ids()) if c]
    if not ids:
        return {"date": _today(), "companies": []}

    conn = bootstrap()
    try:
        today = _today()
        placeholders = ",".join("?" for _ in ids)
        cached: dict[str, dict] = {} if refresh else {
            row["company_id"]: _row_to_briefing(row)
            for row in conn.execute(
                f"SELECT * FROM company_briefings WHERE briefing_date=? "
                f"AND company_id IN ({placeholders})",
                (today, *ids),
            ).fetchall()
        }
        overview_row = None if refresh else conn.execute(
            "SELECT * FROM briefing_overview WHERE briefing_date=?", (today,)
        ).fetchone()

        # The overview reads across every company, so it is only valid alongside a
        # complete set — regenerate the whole day as one unit when either is missing.
        if overview_row is None or any(c not in cached for c in ids):
            inputs = [b for b in (_brief_input(c, conn) for c in ids) if b]
            if inputs:
                overview, companies = _generate(inputs)
                now = datetime.now(SG_TZ).isoformat()
                # The model sometimes returns a subset; backfill the rest so the
                # day's set is always complete and never regenerates on every request.
                returned = {item.get("id") for item in companies}
                companies = list(companies) + [
                    _fallback_briefing(i) for i in inputs if i["id"] not in returned
                ]
                for item in companies:
                    cid = item.get("id")
                    if cid not in ids:
                        continue
                    conn.execute(
                        """
                        INSERT INTO company_briefings
                            (company_id, briefing_date, headline, summary, potential_effects,
                             watch_items, sentiment, generated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(company_id, briefing_date) DO UPDATE SET
                            headline=excluded.headline, summary=excluded.summary,
                            potential_effects=excluded.potential_effects,
                            watch_items=excluded.watch_items, sentiment=excluded.sentiment,
                            generated_at=excluded.generated_at
                        """,
                        (
                            cid, today,
                            str(item.get("headline") or "")[:200],
                            str(item.get("summary") or ""),
                            json.dumps(item.get("potential_effects") or []),
                            json.dumps(item.get("watch_items") or []),
                            str(item.get("sentiment") or "neutral"),
                            now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO briefing_overview
                        (briefing_date, headline, summary, watch_items, generated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(briefing_date) DO UPDATE SET
                        headline=excluded.headline, summary=excluded.summary,
                        watch_items=excluded.watch_items, generated_at=excluded.generated_at
                    """,
                    (
                        today,
                        str(overview.get("headline") or "")[:250],
                        str(overview.get("summary") or ""),
                        json.dumps(overview.get("watch_items") or []),
                        now,
                    ),
                )
                conn.commit()
                for row in conn.execute(
                    f"SELECT * FROM company_briefings WHERE briefing_date=? "
                    f"AND company_id IN ({placeholders})",
                    (today, *ids),
                ).fetchall():
                    cached[row["company_id"]] = _row_to_briefing(row)
                overview_row = conn.execute(
                    "SELECT * FROM briefing_overview WHERE briefing_date=?", (today,)
                ).fetchone()
    finally:
        conn.close()

    return {
        "date": today,
        "overview": _row_to_overview(overview_row) if overview_row else None,
        "companies": [cached[c] for c in ids if c in cached],
    }


def _row_to_overview(row) -> dict:
    return {
        "headline": row["headline"],
        "summary": row["summary"],
        "watchItems": json.loads(row["watch_items"] or "[]"),
        "generatedAt": row["generated_at"],
    }


def _row_to_briefing(row) -> dict:
    return {
        "id": row["company_id"],
        "headline": row["headline"],
        "summary": row["summary"],
        "potentialEffects": json.loads(row["potential_effects"] or "[]"),
        "watchItems": json.loads(row["watch_items"] or "[]"),
        "sentiment": row["sentiment"],
        "generatedAt": row["generated_at"],
    }


def _generate(inputs: list[dict]) -> tuple[dict, list[dict]]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        log.warning("briefing: no OPENROUTER_API_KEY — serving deterministic fallback")
        return _fallback_overview(inputs), [_fallback_briefing(item) for item in inputs]
    try:
        client = OpenRouterLLMClient()
        prompt = PROMPT_TEMPLATE.format(
            companies_json=json.dumps(inputs, ensure_ascii=False)[:12000]
        )
        data = client.complete_json(prompt, max_tokens=2600)
        companies = data.get("companies")
        overview = data.get("overview")
        if not isinstance(companies, list) or not companies:
            raise ValueError("empty briefing response")
        if not isinstance(overview, dict) or not overview.get("summary"):
            overview = _fallback_overview(inputs)
        return overview, companies
    except Exception:
        log.exception("briefing: LLM generation failed — serving deterministic fallback")
        return _fallback_overview(inputs), [_fallback_briefing(item) for item in inputs]


def _fallback_overview(inputs: list[dict]) -> dict:
    total = len(inputs)
    overrated = sum(1 for i in inputs if i.get("quadrant") == "OVERRATED")
    improvers = sum(1 for i in inputs if i.get("isUnderpricedImprover"))
    controversies = sum((i.get("news") or {}).get("controversy") or 0 for i in inputs)
    declining = sum(1 for i in inputs if (i.get("momentum") or 0) < 0)
    return {
        "headline": f"{total} companies covered · {overrated} overrated · {controversies} controversy flags",
        "summary": (
            f"Across the {total} covered companies, {overrated} sit in the Overrated quadrant and "
            f"{declining} show declining evidence momentum. {improvers} currently qualify as "
            f"Underpriced Improvers. {controversies} controversy headlines were flagged this cycle."
        ),
        "watch_items": [],
    }


def _fallback_briefing(item: dict) -> dict:
    """Deterministic, no-LLM fallback so the panel never breaks when
    OPENROUTER_API_KEY is missing or the completion call fails."""
    news = item.get("news") or {}
    controversy = news.get("controversy") or 0
    positive = news.get("positive") or 0
    sentiment = (
        "negative" if controversy > positive
        else "positive" if positive > controversy
        else "neutral"
    )
    headlines = [h.get("title") for h in (news.get("headlines") or [])[:2] if h.get("title")]
    summary = (
        f"Evidence score {item.get('evidenceScore')}, rater consensus {item.get('raterConsensus')}, "
        f"quadrant {item.get('quadrant')}. "
        + (f"Recent headlines: {'; '.join(headlines)}." if headlines else "No fresh scraped headlines this cycle.")
    )
    return {
        "id": item["id"],
        "headline": f"{item.get('name')}: {item.get('quadrant') or 'no signal change'} this week",
        "summary": summary,
        "potential_effects": [],
        "watch_items": [],
        "sentiment": sentiment,
    }
