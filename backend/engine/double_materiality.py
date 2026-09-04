"""double_materiality — the ESRS-style composite that fuses the two halves the app already
computes independently:

  * FINANCIAL materiality (outside-in): the ESG RATING — how agencies price ESG risk back
    into the company. Source: rating_score.py.
  * IMPACT materiality (inside-out): the company's real climate impact, scored as peer-ranked
    CARBON INTENSITY (tCO2e per $M revenue) so a big clean utility beats a small dirty one.
    Source: Climate TRACE emissions (data/climate_trace.py) + Yahoo revenue (data/fundamentals.py).

    composite = w_fin * financial + w_imp * impact - greenwashing_penalty          (0..100)

The blend is finance-tilted (config.DM_WEIGHT_*), because for an equity investor the value
impact outweighs the world impact. The GREENWASHING penalty is the materiality GAP: a company
rated greener than it actually runs (financial >> impact) is flagged, plus any recent
controversy. This is a deterministic, self-contained signal — no web scraping — and it is
exactly what double materiality exists to surface: divergence between reputation and reality.

Nothing is fabricated: a half with no data stays N.A., and the composite is N.A. when the
financial half is missing.
"""
from __future__ import annotations

from typing import Optional

from . import config


def carbon_intensity(emissions_tonnes: Optional[float], market_cap_local: Optional[float],
                     currency: Optional[str]) -> Optional[float]:
    """tCO2e per $M of MARKET CAP — the carbon footprint of a dollar invested (a WACI-style
    measure that is exactly what an equity investor internalises). Market cap is used rather
    than revenue because Yahoo reports revenue in each company's functional currency (USD for
    some ASEAN names) while market cap is reliably in the quote currency, so FX conversion is
    unambiguous. None when inputs are missing or the result is implausible."""
    if not emissions_tonnes or not market_cap_local or market_cap_local <= 0:
        return None
    fx = config.FX_TO_USD.get((currency or "USD").upper())
    if not fx:
        return None
    cap_usd_m = market_cap_local * fx / 1e6
    if cap_usd_m <= 0:
        return None
    intensity = emissions_tonnes / cap_usd_m
    # guard against a stray unit/currency glitch producing a nonsensical rank.
    if not (0 < intensity < 100_000):
        return None
    return round(intensity, 1)


def guard_intensities(intensities: dict[str, Optional[float]]
                      ) -> tuple[dict[str, Optional[float]], set[str]]:
    """Null out implausibly-low intensities (Climate TRACE under-attribution) and return the
    flagged set. A value below DM_INTENSITY_GUARD_FRACTION x the panel MEDIAN is treated as a
    data gap, not a real efficiency: a gas generator does not run 40x cleaner than its peers.
    Needs at least 3 covered names to judge an outlier; below that it passes everything."""
    have = {c: v for c, v in intensities.items() if v is not None}
    if len(have) < 3:
        return dict(intensities), set()
    ordered = sorted(have.values())
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    floor = config.DM_INTENSITY_GUARD_FRACTION * median
    flagged = {c for c, v in have.items() if v < floor}
    cleaned = {c: (None if c in flagged else v) for c, v in intensities.items()}
    return cleaned, flagged


def impact_scores(intensities: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """Map each company's carbon intensity to a 0..100 impact score by peer RANK — lower
    intensity (cleaner) ranks higher. Companies without an intensity get None."""
    have = {cid: v for cid, v in intensities.items() if v is not None}
    out: dict[str, Optional[float]] = {cid: None for cid in intensities}
    n = len(have)
    if n == 0:
        return out
    if n == 1:
        # a single covered name cannot be ranked against peers; place it at the midpoint.
        (only,) = have
        out[only] = 50.0
        return out
    # rank ascending by intensity (cleanest first); best -> 100, worst -> 0.
    ordered = sorted(have, key=lambda c: have[c])
    for i, cid in enumerate(ordered):
        out[cid] = round(100.0 * (n - 1 - i) / (n - 1), 1)
    return out


def greenwashing_penalty(financial: Optional[float], impact: Optional[float],
                         controversies: int = 0) -> tuple[float, list[dict]]:
    """The materiality-gap penalty + its drivers. Rated greener than it runs, plus any
    recent controversy. Returns (penalty, drivers)."""
    drivers: list[dict] = []
    penalty = 0.0
    if financial is not None and impact is not None:
        gap = max(0.0, financial - impact)
        if gap > 0:
            pts = round(config.GREENWASH_GAP_K * gap, 1)
            penalty += pts
            drivers.append({
                "label": "Materiality gap",
                "points": pts,
                "detail": f"Rated {financial:.0f}/100 on ESG but runs at {impact:.0f}/100 on "
                          f"actual carbon intensity — a {gap:.0f}-point reputation-vs-reality gap.",
            })
    if controversies > 0:
        pts = round(controversies * config.GREENWASH_CONTROVERSY_PTS, 1)
        penalty += pts
        drivers.append({
            "label": "Recent controversies",
            "points": pts,
            "detail": f"{controversies} recent ESG controversy headline(s).",
        })
    return round(min(penalty, config.GREENWASH_CAP), 1), drivers


def composite(financial: Optional[float], impact: Optional[float],
              penalty: float) -> tuple[Optional[float], Optional[str]]:
    """Blend the two halves (finance-tilted) and subtract the penalty. Returns
    (composite, note). If impact is N.A., the composite falls back to the financial half
    alone and says so; if financial is N.A., the composite is N.A."""
    wf, wi = config.DM_WEIGHT_FINANCIAL, config.DM_WEIGHT_IMPACT
    if financial is None:
        return None, "No ESG rating — the financial-materiality half is N.A."
    if impact is None:
        val = max(0.0, min(100.0, financial - penalty))
        return round(val, 1), "No impact score (no emissions/revenue match) — composite is the financial half only."
    blended = wf * financial + wi * impact
    val = max(0.0, min(100.0, blended - penalty))
    return round(val, 1), None
