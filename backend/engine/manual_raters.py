"""REAL rater ratings typed in by a human, with provenance.

S&P Global and Sustainalytics publish current ratings on free public pages; what their
terms forbid is BULK automated scraping, which is also why the pages are JS-gated. At ten
companies the honest path is a person reading the page and recording what they saw — the
value on the rater's own scale, the URL, and the date they read it. Those rows are REAL:
they count towards MIN_REAL_RATERS_FOR_DIVERGENCE just like a scrape does.

Precedence at ingest: manual > scraped (data/realraters.py) > seeded.

One observation is one observation. It lands on the ASSESSMENT YEAR the rater states --
the same discipline realratings.py applies to report-disclosed ratings, and the reason a
2025 S&P score does not get filed under 2023. It is never spread across other years
(that would be fabricating history, guardrail T7). The year defaults to END_YEAR.

Storage is `manual_rater_scores`, user-authored and deliberately outside db.TABLES so a
reset() never wipes it — same reasoning as `industry_benchmarks`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from . import config
from .db import bootstrap
from .rater_overlay import FIELD, RATERS, typed_value  # noqa: F401  (re-exported)

SCALE_HELP = {
    "msci": "a letter CCC..AAA",
    "sustainalytics": f"an ESG Risk Rating 0..{config.SUSTAINALYTICS_MAX:g} (LOWER = better)",
    "sp": f"an ESG Score 0..{config.SP_GLOBAL_MAX:g} (higher = better)",
    "cdp": "a climate score D-..A",
}


def _clean_value(rater: str, value_raw: Any) -> str:
    """Validate against that rater's OWN scale; return the canonical stored string."""
    text = str(value_raw if value_raw is not None else "").strip()
    if not text:
        raise ValueError(f"value must be {SCALE_HELP[rater]}")
    if rater == "msci":
        letter = text.upper()
        if letter not in config.MSCI_LETTER_TO_NUM:
            raise ValueError(f"MSCI value must be {SCALE_HELP['msci']}")
        return letter
    if rater == "cdp":
        letter = text.upper()
        if letter not in config.CDP_LETTER_TO_NUM:
            raise ValueError(f"CDP value must be {SCALE_HELP['cdp']}")
        return letter
    top = config.SUSTAINALYTICS_MAX if rater == "sustainalytics" else config.SP_GLOBAL_MAX
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{rater} value must be {SCALE_HELP[rater]}") from exc
    if not 0.0 <= number <= top:
        raise ValueError(f"{rater} value must be {SCALE_HELP[rater]}")
    return f"{round(number, 2):g}"


def _clean_year(assessment_year) -> int:
    """The year the rating is FOR. Defaults to the analysis year; bounded so a typo cannot
    file a rating outside any window we could honestly show it in."""
    if assessment_year in (None, ""):
        return config.END_YEAR
    try:
        year = int(assessment_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("assessment_year must be a year like 2025") from exc
    if not config.START_YEAR <= year <= config.CURRENT_YEAR:
        raise ValueError(
            f"assessment_year must be between {config.START_YEAR} and {config.CURRENT_YEAR}")
    return year


def _clean_provenance(observed_on: str, source_url: str) -> tuple[str, str]:
    """A hand-entered rating without provenance is not real — refuse it."""
    observed_on = (observed_on or "").strip()
    source_url = (source_url or "").strip()
    try:
        observed = date.fromisoformat(observed_on)
    except ValueError as exc:
        raise ValueError("observed_on must be an ISO date (YYYY-MM-DD)") from exc
    if observed > date.today():
        raise ValueError("observed_on cannot be in the future")
    if not source_url.lower().startswith(("http://", "https://")):
        raise ValueError("source_url must be the rater page you read the value on")
    return observed_on, source_url


def get_manual_raters() -> list[dict[str, Any]]:
    """Every hand-entered rating, newest scale-checked value first by company."""
    conn = bootstrap()
    try:
        rows = conn.execute(
            "SELECT * FROM manual_rater_scores ORDER BY company_id, rater").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def by_company() -> dict[str, dict[str, dict[str, Any]]]:
    """{company_id: {rater: row}} — the shape the ingest overlay and the realness
    tracking both want."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in get_manual_raters():
        out.setdefault(row["company_id"], {})[row["rater"]] = row
    return out


def real_keys_by_company_year() -> dict[str, dict[int, list[str]]]:
    """{company_id: {assessment_year: [rater, ...]}} a human has vouched for."""
    out: dict[str, dict[int, list[str]]] = {}
    for cid, entries in by_company().items():
        for rater, row in entries.items():
            year = row.get("assessment_year") or config.END_YEAR
            out.setdefault(cid, {}).setdefault(year, []).append(rater)
    return {cid: {y: sorted(v) for y, v in years.items()} for cid, years in out.items()}


def overlay(raters: list) -> list:
    """Replace values with hand-entered ones where they exist.

    `raters` is a list of RaterRow. Runs LAST of all the overlays, so a human reading the
    rater page beats every automated source, and each entry lands only on its own
    assessment year -- a single observation is never backfilled across the window.
    """
    from .rater_overlay import apply

    manual = by_company()
    if not manual:
        return raters
    by_cid_year: dict[str, dict[int, dict]] = {}
    for cid, entries in manual.items():
        for rater, row in entries.items():
            year = row.get("assessment_year") or config.END_YEAR
            by_cid_year.setdefault(cid, {}).setdefault(year, {})[rater] = row["value_raw"]
    return apply(raters, by_cid_year)


def set_manual_rater(company_id: str, rater: str, value_raw: Any, observed_on: str,
                     source_url: str, note: Optional[str] = None,
                     assessment_year: Any = None) -> list[dict[str, Any]]:
    """Store (or replace) one hand-entered rating."""
    company_id = (company_id or "").strip()
    rater = (rater or "").strip().lower()
    if rater not in RATERS:
        raise ValueError(f"rater must be one of {', '.join(RATERS)}")
    if company_id not in _known_companies():
        raise ValueError(f"unknown company_id {company_id!r}")
    value = _clean_value(rater, value_raw)
    year = _clean_year(assessment_year)
    observed_on, source_url = _clean_provenance(observed_on, source_url)
    conn = bootstrap()
    try:
        conn.execute(
            """
            INSERT INTO manual_rater_scores
                (company_id, rater, value_raw, assessment_year, observed_on,
                 source_url, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, rater) DO UPDATE SET
                value_raw=excluded.value_raw,
                assessment_year=excluded.assessment_year,
                observed_on=excluded.observed_on,
                source_url=excluded.source_url,
                note=excluded.note,
                updated_at=excluded.updated_at
            """,
            (company_id, rater, value, year, observed_on, source_url,
             (note or "").strip() or None, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_manual_raters()


def delete_manual_rater(company_id: str, rater: str) -> list[dict[str, Any]]:
    """Drop one hand-entered rating; the channel reverts to scraped, then seeded."""
    conn = bootstrap()
    try:
        cur = conn.execute(
            "DELETE FROM manual_rater_scores WHERE company_id=? AND rater=?", (company_id, rater))
        if not cur.rowcount:
            raise KeyError(f"{company_id}/{rater}")
        conn.commit()
    finally:
        conn.close()
    return get_manual_raters()


def _known_companies() -> set[str]:
    conn = bootstrap()
    try:
        return {r["company_id"] for r in conn.execute("SELECT company_id FROM universe")}
    finally:
        conn.close()
