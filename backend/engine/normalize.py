"""Rater normalization — make all three raters point the SAME way (higher=better),
then percentile-rank within the panel × sector.

Common failure points this guards (build-spec §6):
  * Sustainalytics is a RISK score (lower=better) -> inverted here (T2).
  * Comparison is by percentile RANK, never raw scale (T6).
  * The three raters are never blended into one number.
  * A rank over a handful of names is noise -> N.A. below MIN_PEERS_FOR_SECTOR_RANK.
  * Which channels are REAL is tracked here, so consensus/divergence can refuse to
    blend a real rating with an illustrative one.

KNOWN LIMIT: a percentile is a rank inside the cohort's values, and for a channel that is
only partly covered by real ratings that cohort still contains illustrative values. The
rank is therefore real-vs-mixed; only the REAL channels feed consensus/divergence, and
`basis`/`peers` ship so the UI can say what the number is relative to.

Ranking real values against real values ONLY was measured. Where it is needed it is
already true, and where it is not true it cannot be afforded:

  * 2024 and 2025 have NO seeded rows at all — those years exist only because a real
    observation created them (see rater_overlay.apply). Every population there is
    real-only by construction: cdp 7 of 7 real, msci 4 of 4 (2024) and 1 of 1 (2025).
  * 2019-2023 is the seeded window: 0 of 10 values are real on msci / sp / sustainalytics,
    and cdp has 2 of 2 (below the peer floor either way, so already N.A.).

So a strict real-only rule would change nothing except blanking the illustrative ranks in
the seeded window, which are already labelled illustrative and already excluded from
consensus and divergence. The mixed-population caveat therefore applies ONLY to 2019-2023.

CDP needs no such rule ever: there is no seeded CDP column anywhere, so every CDP value is
real by construction. Keep it that way — seeding CDP would silently convert a real rank
into a mixed one.
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


def cdp_to_num(letter: Optional[str]) -> Optional[float]:
    """CDP climate score D-..A -> 1..8 (already higher = better)."""
    if letter is None:
        return None
    return config.CDP_LETTER_TO_NUM.get(letter.strip().upper())


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


def _population(ds: Dataset, sector: str, year: int, getter) -> tuple[list[float], str]:
    """All higher=better values for a rater within a sector-year; fall back to the whole
    panel when the sector is too thin. The basis label comes back too, so the UI can say
    what a percentile is relative to."""
    rows_by_sector = [r for r in ds.raters if r.year == year and ds.companies[r.company_id].sector == sector]
    vals = [v for v in (getter(r) for r in rows_by_sector) if v is not None]
    if len(vals) >= config.MIN_PEERS_FOR_SECTOR_RANK:
        return vals, sector
    all_rows = [r for r in ds.raters if r.year == year]
    return [v for v in (getter(r) for r in all_rows) if v is not None], "all companies"


def real_raters_cache() -> dict:
    """{cid: {"msci": letter, ...}} of scraped ratings, or {} when nothing is cached."""
    try:
        from backend.data.realraters import cached_real_raters

        return cached_real_raters()
    except Exception:
        return {}


def report_raters_cache() -> dict[str, dict[int, list[str]]]:
    """{cid: {assessment_year: [rater, ...]}} vouched for by a real, dated source: the
    companies' own reports, plus CDP's public scores table. "Did not disclose" is not in
    here — declining to answer is not a rating."""
    out: dict[str, dict[int, list[str]]] = {}
    for loader in ("backend.data.realratings", "backend.data.realcdp"):
        try:
            module = __import__(loader, fromlist=["scored_by_year"])
            for cid, years in module.scored_by_year().items():
                for year, entries in years.items():
                    keys = set(out.setdefault(cid, {}).get(year) or [])
                    out[cid][year] = sorted(keys | set(entries))
        except Exception:
            continue
    return out


def manual_raters_cache() -> dict[str, dict[int, list[str]]]:
    """{cid: {assessment_year: [rater, ...]}} a human has entered by hand."""
    try:
        from .manual_raters import real_keys_by_company_year

        return real_keys_by_company_year()
    except Exception:
        return {}


def real_rater_keys(cid: str, year: int, real: Optional[dict] = None,
                    manual: Optional[dict] = None, report: Optional[dict] = None) -> list[str]:
    """Rater channels carrying a REAL value for this company-year.

    Three sources, none of them a hardcoded company list — if a store grows, this grows
    with it:
      * ratings the company disclosed in THAT year's own report (per assessment year, so
        earlier years can be real too);
      * hand-entered rows with provenance, on the assessment year the reader recorded;
      * the KnowESG MSCI scrape, which is END_YEAR-only AND excluded unless
        config.TRUST_SCRAPED_RATERS_AS_REAL says otherwise: KnowESG has since dropped its
        numeric scores, so the cached letters can no longer be reproduced or dated.
    """
    keys = set((report_raters_cache() if report is None else report).get(cid, {}).get(year) or [])
    keys.update((manual_raters_cache() if manual is None else manual).get(cid, {}).get(year) or [])
    if year == config.END_YEAR:
        if (config.TRUST_SCRAPED_RATERS_AS_REAL
                and ((real_raters_cache() if real is None else real).get(cid) or {}).get("msci")):
            keys.add("msci")
    return sorted(keys)


def normalize_raters(ds: Dataset, year: int = config.END_YEAR) -> dict[str, RaterPercentiles]:
    """Return per-company percentiles for a given year (all higher=better)."""
    getters = {
        "msci": lambda r: msci_to_num(r.msci_letter),
        "sust": lambda r: sustainalytics_to_num(r.sustainalytics_risk),
        "sp": lambda r: (None if r.sp_global is None else float(r.sp_global)),
        "cdp": lambda r: cdp_to_num(r.cdp_letter),
    }
    real = real_raters_cache()          # read every store once, not once per company
    manual = manual_raters_cache()
    report = report_raters_cache()
    out: dict[str, RaterPercentiles] = {}
    for cid, comp in ds.companies.items():
        row = next((r for r in ds.raters if r.company_id == cid and r.year == year), None)
        if row is None:
            out[cid] = RaterPercentiles(company_id=cid)
            continue
        pct, basis, peers = {}, None, None
        for key, get in getters.items():
            v = get(row)
            pop, pop_basis = ([], None) if v is None else _population(ds, comp.sector, year, get)
            if v is None or len(pop) < config.MIN_PEERS_FOR_SECTOR_RANK:
                pct[key] = None          # too few peers to rank against -> N.A., not a guess
                continue
            pct[key] = round(_percentile(pop, v), 2)
            if basis is None:            # all channels share the cohort rule; report the first
                basis, peers = pop_basis, len(pop)
        out[cid] = RaterPercentiles(company_id=cid, msci_pct=pct["msci"],
                                    sp_pct=pct["sp"], sustainalytics_pct=pct["sust"],
                                    cdp_pct=pct["cdp"],
                                    real_raters=real_rater_keys(cid, year, real, manual, report),
                                    basis=basis, peers=peers)
    return out


def consensus(p: RaterPercentiles) -> Optional[float]:
    """Mean of the contributing rater percentiles.

    With config.ALLOW_ILLUSTRATIVE_FALLBACK on (the prototype default) that is every
    available channel, real or seeded, and `p.provenance()` says which. In strict mode
    only REAL channels contribute and the mean is N.A. below
    MIN_REAL_RATERS_FOR_DIVERGENCE — a mean of one real rating and two seeded ones is not
    a consensus, and strict mode refuses to imply otherwise.
    """
    values = p.contributing_values()
    if not values:
        return None
    if (not config.ALLOW_ILLUSTRATIVE_FALLBACK
            and len(values) < config.MIN_REAL_RATERS_FOR_DIVERGENCE):
        return None
    return round(sum(values) / len(values), 2)
