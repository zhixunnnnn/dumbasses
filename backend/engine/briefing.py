"""Monday-morning manager briefing.

An LLM-synthesized digest of live news + verified-evidence signals for every
company the Evidence Dashboard covers, cached once per Asia/Singapore
calendar day so the dashboard loads instantly after the first request each
day (see backend/app/main.py: GET /api/dashboard/briefing).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .db import bootstrap
from .llm import OpenRouterLLMClient

SG_TZ = ZoneInfo("Asia/Singapore")


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

For EACH company, write a manager-ready briefing. Be specific and use the numbers given — do \
not invent facts not present in the data. If news is null or headlines are empty, say so \
plainly rather than fabricating events.

Return strict JSON: {{"companies": [{{
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


def get_or_generate_briefings(company_ids: list[str] | None = None) -> dict:
    ids = [c for c in dict.fromkeys(company_ids or _all_company_ids()) if c]
    if not ids:
        return {"date": _today(), "companies": []}

    conn = bootstrap()
    try:
        today = _today()
        placeholders = ",".join("?" for _ in ids)
        cached: dict[str, dict] = {
            row["company_id"]: _row_to_briefing(row)
            for row in conn.execute(
                f"SELECT * FROM company_briefings WHERE briefing_date=? "
                f"AND company_id IN ({placeholders})",
                (today, *ids),
            ).fetchall()
        }

        missing = [c for c in ids if c not in cached]
        if missing:
            inputs = [b for b in (_brief_input(c, conn) for c in missing) if b]
            if inputs:
                for item in _generate(inputs):
                    cid = item.get("id")
                    if cid not in missing:
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
                            datetime.now(SG_TZ).isoformat(),
                        ),
                    )
                conn.commit()
                missing_placeholders = ",".join("?" for _ in missing)
                for row in conn.execute(
                    f"SELECT * FROM company_briefings WHERE briefing_date=? "
                    f"AND company_id IN ({missing_placeholders})",
                    (today, *missing),
                ).fetchall():
                    cached[row["company_id"]] = _row_to_briefing(row)
    finally:
        conn.close()

    return {"date": today, "companies": [cached[c] for c in ids if c in cached]}


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


def _generate(inputs: list[dict]) -> list[dict]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        return [_fallback_briefing(item) for item in inputs]
    try:
        client = OpenRouterLLMClient()
        prompt = PROMPT_TEMPLATE.format(
            companies_json=json.dumps(inputs, ensure_ascii=False)[:12000]
        )
        data = client.complete_json(prompt, max_tokens=2200)
        companies = data.get("companies")
        if not isinstance(companies, list) or not companies:
            raise ValueError("empty briefing response")
        return companies
    except Exception:
        return [_fallback_briefing(item) for item in inputs]


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
