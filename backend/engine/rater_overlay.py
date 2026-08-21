"""Shared plumbing for laying REAL rater values over the seeded rows.

Three sources overlay the seed, in this precedence (lowest first):

    seeded -> KnowESG scrape -> CDP scores table -> report-disclosed -> hand-entered

Each is applied in that order by ingest.load, so a later source simply overwrites the
channel it covers. This module owns the bit they all share: which RaterRow field a rater
channel maps to, and how to apply a {company: {year: {rater: value}}} map.

A real observation is never discarded because the seed did not anticipate its year: if a
company-year has no seeded row, one is CREATED carrying only the real channels (every
other channel None). That is how a 2025 CDP score survives a window that stops at 2023.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

RATERS = ("msci", "sustainalytics", "sp", "cdp")

# rater -> the RaterRow field it overlays. Sustainalytics stays on its native RISK scale
# here; normalize.sustainalytics_to_num does the inversion, exactly as for seeded rows.
FIELD = {
    "msci": "msci_letter",
    "sustainalytics": "sustainalytics_risk",
    "sp": "sp_global",
    "cdp": "cdp_letter",
}


def typed_value(rater: str, value_raw: Any) -> Optional[float | str]:
    """A stored string back on the scale RaterRow expects (letters stay letters)."""
    if rater in ("msci", "cdp"):
        return value_raw
    try:
        return float(value_raw)
    except (TypeError, ValueError):
        return None


def apply(raters: list, by_cid_year: dict[str, dict[int, dict[str, Any]]]) -> list:
    """Overlay {cid: {year: {rater: value_raw}}} onto `raters`, adding rows for
    company-years the seed does not cover. Returns a new list; input is untouched."""
    if not by_cid_year:
        return raters
    row_class = type(raters[0]) if raters else None
    out, seen = [], set()
    for r in raters:
        entries = by_cid_year.get(r.company_id, {}).get(r.year)
        seen.add((r.company_id, r.year))
        if not entries:
            out.append(r)
            continue
        fields = {FIELD[rater]: typed_value(rater, value)
                  for rater, value in entries.items() if rater in FIELD}
        out.append(replace(r, **fields))
    if row_class is None:
        return out
    for cid, years in by_cid_year.items():          # real years the seed never had
        for year, entries in years.items():
            if (cid, year) in seen:
                continue
            fields = {"msci_letter": None, "sustainalytics_risk": None, "sp_global": None}
            fields.update({FIELD[rater]: typed_value(rater, value)
                           for rater, value in entries.items() if rater in FIELD})
            out.append(row_class(company_id=cid, year=year, **fields))
    return out
