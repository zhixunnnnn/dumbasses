"""REAL Sustainalytics ESG Risk Ratings, hand-recorded with provenance.

Sustainalytics retired its free numeric lookup and Yahoo removed its sustainability tab, so
the reliable public surface for these values is the Morningstar Sustainalytics rating page
(Morningstar distributes Sustainalytics). This module carries the values a reader recorded
from those pages — the value on Sustainalytics' own RISK scale (lower = better), the page
URL, and the date read — the same honest "a person read the page" path manual_raters uses.

It plugs into the engine exactly like realcdp: `scored_by_year()` marks the channel REAL for
its assessment year (so provenance stops saying "illustrative"), and `overlay()` writes the
value onto each RaterRow via rater_overlay.apply. The assessment year is the rating's own
year (2026), never re-dated onto the 2023 analysis window — normalize.py already reads a
channel at the latest year it carries a real observation, the same way it handles a real 2024
MSCI letter or a 2025 CDP score.

A company Morningstar does not rate is simply absent here and keeps its seeded value — never
a fabricated one (guardrail T7).
"""
from __future__ import annotations

import json

from backend.engine import config

_FILE = config.DATA_DIR / "real_sustainalytics.json"


def _blob() -> dict:
    try:
        return json.loads(_FILE.read_text("utf-8"))
    except Exception:
        return {}


def scored_by_year() -> dict[str, dict[int, dict[str, float]]]:
    """{cid: {assessment_year: {"sustainalytics": value}}} for the companies we have a real,
    dated Sustainalytics ESG Risk Rating for."""
    blob = _blob()
    year = blob.get("assessment_year", config.END_YEAR)
    out: dict[str, dict[int, dict[str, float]]] = {}
    for cid, info in (blob.get("companies") or {}).items():
        val = info.get("value")
        if val is not None:
            out.setdefault(cid, {})[int(year)] = {"sustainalytics": float(val)}
    return out


def overlay(raters: list) -> list:
    """Overlay the real Sustainalytics risk values onto their own assessment year. Applied
    after the report-disclosed overlay and before manual (manual still wins), matching the
    precedence the other real sources use."""
    from backend.engine.rater_overlay import apply

    return apply(raters, scored_by_year())


def provenance_for(cid: str) -> dict | None:
    """The source URL + observed date for one company's real Sustainalytics value, for the UI."""
    blob = _blob()
    info = (blob.get("companies") or {}).get(cid)
    if not info:
        return None
    return {"value": info.get("value"), "url": info.get("url"),
            "observed_on": blob.get("observed_on"), "source": blob.get("source")}


if __name__ == "__main__":
    print(json.dumps(scored_by_year(), indent=1))
