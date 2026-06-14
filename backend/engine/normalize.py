"""Rater normalization — make all three raters point the SAME way (higher=better),
then percentile-rank within the reference panel × sector.

Common failure points this guards (build-spec §6):
  * Sustainalytics is a RISK score (lower=better) -> inverted here (T2).
  * Comparison is by percentile RANK, never raw scale (T6).
  * The three raters are never blended into one number.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .ingest import Dataset, RaterRow
from .models import RaterPercentiles


def msci_to_num(letter: Optional[str]) -> Optional[float]:
    if letter is None:
        return None
    return config.MSCI_LETTER_TO_NUM.get(letter.strip().upper())


def sustainalytics_to_num(risk: Optional[float]) -> Optional[float]:
    """Invert risk so higher = better (the single most common bug)."""
    if risk is None:
        return None
    return config.SUSTAINALYTICS_MAX - float(risk)


def _percentile(pop: list[float], value: float) -> float:
    """Mean-rank percentile of `value` within `pop` (0..100, higher=better)."""
    if not pop:
        return 50.0
    below = sum(1 for x in pop if x < value)
    equal = sum(1 for x in pop if x == value)
    return 100.0 * (below + 0.5 * equal) / len(pop)


def _population(ds: Dataset, sector: str, year: int, getter) -> list[float]:
    """All higher=better values for a rater within a sector-year; fall back to whole panel."""
    rows_by_sector = [r for r in ds.raters if r.year == year and ds.companies[r.company_id].sector == sector]
    vals = [v for v in (getter(r) for r in rows_by_sector) if v is not None]
    if len(vals) < config.MIN_PEERS_FOR_SECTOR_RANK:
        all_rows = [r for r in ds.raters if r.year == year]
        vals = [v for v in (getter(r) for r in all_rows) if v is not None]
    return vals


def normalize_raters(ds: Dataset, year: int = config.END_YEAR) -> dict[str, RaterPercentiles]:
    """Return per-company percentiles for a given year (all higher=better)."""
    getters = {
        "msci": lambda r: msci_to_num(r.msci_letter),
        "sust": lambda r: sustainalytics_to_num(r.sustainalytics_risk),
        "sp": lambda r: (None if r.sp_global is None else float(r.sp_global)),
    }
    out: dict[str, RaterPercentiles] = {}
    for cid, comp in ds.companies.items():
        row = next((r for r in ds.raters if r.company_id == cid and r.year == year), None)
        if row is None:
            out[cid] = RaterPercentiles(company_id=cid)
            continue
        pct = {}
        for key, get in getters.items():
            v = get(row)
            if v is None:
                pct[key] = None
            else:
                pop = _population(ds, comp.sector, year, get)
                pct[key] = round(_percentile(pop, v), 2)
        out[cid] = RaterPercentiles(company_id=cid, msci_pct=pct["msci"],
                                    sp_pct=pct["sp"], sustainalytics_pct=pct["sust"])
    return out


def consensus(p: RaterPercentiles) -> Optional[float]:
    """Mean of available percentiles (>=1). None if no rater covers the name."""
    avail = p.available()
    return round(sum(avail) / len(avail), 2) if avail else None
