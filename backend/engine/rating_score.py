"""rating_score — the ESG *rating* score: an agency-consensus number on one 0..100
quality scale, SASB-material-weighted.

This is the method ported from the `smartass` app (scoring/normalize.py + scoring/score.py):

    rating = Σ_covered ( weight_t / covered_weight ) · topic_score_t          (0..100)
    topic_score_t = mean over agencies of that agency's normalized score for topic t's pillar

Unlike evidence_score (which reads the company's OWN disclosures), this reads the rating
AGENCIES — MSCI, S&P Global, Sustainalytics and CDP — normalized to one higher=better
scale. It is what a market participant actually reacts to, which is why it is the headline
number in the investor-facing UI.

Two deliberate choices:
  * ABSOLUTE quality scale (AA -> 85.7), not the percentile rank the Trust Meter uses. A
    standalone "72/100" reads as a rating; a percentile within ten peers does not.
  * CDP is a climate score, so it informs ONLY the Environmental pillar. For an E-dominant
    industry like power generation this is what makes the SASB weighting actually bite —
    otherwise, with agencies publishing only headlines, the weighting collapses to a plain
    mean (the same limitation the smartass app has).

No agency rates the company -> total is config.NA (never a fabricated 0). Provenance is
inherited from the same contributing set the consensus/divergence figures use, so one
label describes the rating, the consensus and the divergence together.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .ingest import Dataset, RaterRow
from .models import RaterPercentiles, RatingScore, TraceNode
from .normalize import normalize_raters
from .sasb import topics_for
from .trace import leaf

# Which pillars each agency's headline informs. CDP -> Environmental only (it is a climate
# score); the broad ESG raters inform all three because they publish a single headline.
# S&P Global is intentionally absent: its score pages are not publicly obtainable (Akamai-
# gated), so — as in the smartass app — it never contributes a real number and is dropped.
AGENCY_PILLARS: dict[str, tuple[str, ...]] = {
    "msci": ("E", "S", "G"),
    "sustainalytics": ("E", "S", "G"),
    "cdp": ("E",),
}
AGENCY_LABEL = {"msci": "MSCI", "sustainalytics": "Sustainalytics", "cdp": "CDP"}

_MSCI_MAX = max(config.MSCI_LETTER_TO_NUM.values())   # AAA
_CDP_MAX = max(config.CDP_LETTER_TO_NUM.values())     # A


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


_TOPIC_LABELS = {
    "ghg_emissions": "GHG emissions",
    "energy_transition": "Energy transition",
    "workforce_safety": "Workforce safety",
    "air_quality": "Air quality",
    "water_management": "Water management",
    "grid_resiliency": "Grid resiliency",
}


def _pretty_topic(topic_id: str) -> str:
    return _TOPIC_LABELS.get(topic_id, topic_id.replace("_", " ").capitalize())


def agency_quality(channel: str, row: RaterRow) -> Optional[float]:
    """One agency's rating on the 0..100 higher=better quality scale, or None if absent.

    MSCI/CDP letters spread evenly over the scale (AAA=100, AA=85.7 ... ; A=100 ... D-=12.5).
    S&P Global is already 0..100. Sustainalytics is a RISK score -> inverted (MAX - risk),
    matching engine.normalize.sustainalytics_to_num so the two views never disagree in sign.
    """
    if channel == "msci":
        num = config.MSCI_LETTER_TO_NUM.get((row.msci_letter or "").strip().upper())
        return None if num is None else round(num / _MSCI_MAX * 100.0, 1)
    if channel == "cdp":
        num = config.CDP_LETTER_TO_NUM.get((row.cdp_letter or "").strip().upper())
        return None if num is None else round(num / _CDP_MAX * 100.0, 1)
    if channel == "sp":
        return None if row.sp_global is None else _clamp(float(row.sp_global))
    if channel == "sustainalytics":
        risk = row.sustainalytics_risk
        return None if risk is None else _clamp(config.SUSTAINALYTICS_MAX - float(risk))
    return None


def _chosen_qualities(ds: Dataset, cid: str, pcts: RaterPercentiles) -> dict[str, dict]:
    """{channel: {"quality": float, "year": int, "real": bool}} for every channel the
    percentile view found a rankable value on. Reads the RAW agency value at the SAME year
    the Trust Meter ranked it (pcts.rater_years), so the absolute score and the percentile
    view are always talking about the same observation."""
    rows = {r.year: r for r in ds.raters if r.company_id == cid}
    # REAL channels only — no illustrative/seeded rating ever enters the score. An agency that
    # is not a real, dated observation for this company is dropped; the pillar then relies on
    # whatever real inputs remain, or is N.A. (never a fabricated fill).
    present = {k: v for k, v in pcts._by_key().items()
               if v is not None and k in AGENCY_PILLARS and k in pcts.real_raters}
    out: dict[str, dict] = {}
    for channel in present:
        year = pcts.rater_years.get(channel, config.END_YEAR)
        row = rows.get(year)
        if row is None:
            continue
        q = agency_quality(channel, row)
        if q is None:
            continue
        out[channel] = {"quality": q, "year": year, "real": True}
    return out


def environmental_signal(ds: Dataset, cid: str,
                         impact_score: Optional[float]) -> tuple[Optional[float], list[str]]:
    """An OBJECTIVE Environmental-pillar score (0..100) built from evidence, not agency
    opinion: the company's latest real CDP climate grade and its peer-ranked Climate TRACE
    carbon intensity (impact_score), averaged over whichever are available. None when neither
    exists (the E pillar then falls back to the agency headline)."""
    cdp_rows = [r for r in ds.raters if r.company_id == cid and r.cdp_letter]
    cdp_q = agency_quality("cdp", max(cdp_rows, key=lambda r: r.year)) if cdp_rows else None
    parts, sources = [], []
    if cdp_q is not None:
        parts.append(cdp_q)
        sources.append("CDP")
    if impact_score is not None:
        parts.append(impact_score)
        sources.append("Climate TRACE intensity")
    if not parts:
        return None, []
    return round(sum(parts) / len(parts), 1), sources


def rating_from_pcts(ds: Dataset, cid: str, year: int, pcts: RaterPercentiles,
                     env_signal: Optional[float] = None,
                     env_sources: Optional[list[str]] = None,
                     s_signal: Optional[float] = None,
                     s_sources: Optional[list[str]] = None,
                     g_signal: Optional[float] = None,
                     g_sources: Optional[list[str]] = None) -> RatingScore:
    """The ESG rating. A pillar is driven by OBJECTIVE, REAL evidence whenever we have it,
    and only falls back to the rating agencies (as a reference) when we don't:
      * Environmental — CDP grade + real Climate TRACE carbon intensity (`env_signal`);
      * Social — the company's real workforce-safety disclosures (`s_signal`);
      * Governance — the company's real grid-resiliency disclosures (`g_signal`).
    Agencies (MSCI/Sustainalytics) are a REFERENCE for any pillar with no real signal, since
    their differing black-box methods are only comparable as a rough guide. A pillar with no
    real signal and no agency stays N.A."""
    comp = ds.company(cid)
    topics = topics_for(comp.sasb_industry)
    qualities = _chosen_qualities(ds, cid, pcts)

    # per-agency pillar map: each agency's quality applied to the pillars it informs.
    per_agency_pillars: dict[str, dict[str, float]] = {}
    for channel, info in qualities.items():
        pillars = AGENCY_PILLARS.get(channel, ("E", "S", "G"))
        per_agency_pillars[channel] = {p: info["quality"] for p in pillars}

    # topic score = mean over agencies of that agency's value for the topic's pillar.
    topic_scores: dict[str, Optional[float]] = {}
    topic_sources: dict[str, list[str]] = {}
    for t in topics:
        pillar = t["pillar"]
        vals, srcs = [], []
        for channel, pmap in per_agency_pillars.items():
            if pillar in pmap:
                vals.append(pmap[pillar])
                srcs.append(channel)
        topic_scores[t["topic_id"]] = round(sum(vals) / len(vals), 1) if vals else None
        topic_sources[t["topic_id"]] = srcs

    # OBJECTIVE per-pillar overrides: real evidence replaces the agency headline for that
    # pillar's topics, so each pillar reflects measured performance and stops mirroring the
    # others. A pillar with no real signal keeps the agency reference.
    overrides = {"E": (env_signal, env_sources), "S": (s_signal, s_sources),
                 "G": (g_signal, g_sources)}
    for pillar, (sig, srcs) in overrides.items():
        if sig is None:
            continue
        for t in topics:
            if t["pillar"] == pillar:
                topic_scores[t["topic_id"]] = round(sig, 1)
                topic_sources[t["topic_id"]] = srcs or ["objective"]

    total_weight = sum(t["weight"] for t in topics)
    covered_weight = sum(t["weight"] for t in topics if topic_scores.get(t["topic_id"]) is not None)

    if covered_weight == 0:
        empty = TraceNode(label=f"ESG rating {year} — no agency coverage", value=config.NA)
        return RatingScore(company_id=cid, year=year, total=config.NA,
                           pillars={"E": config.NA, "S": config.NA, "G": config.NA},
                           coverage=0.0, agencies=[], provenance=None, trace=empty)

    # renormalize weights over covered topics so the score stays 0..100.
    score = 0.0
    contributions: dict[str, float] = {}
    for t in topics:
        ts = topic_scores.get(t["topic_id"])
        if ts is None:
            continue
        contrib = (t["weight"] / covered_weight) * ts
        contributions[t["topic_id"]] = round(contrib, 2)
        score += contrib

    pillars = _pillar_scores(per_agency_pillars)
    for pillar, (sig, _srcs) in overrides.items():
        if sig is not None:
            pillars[pillar] = round(sig, 1)   # objective/real signal, not the agency average
    trace = _build_trace(year, round(score, 1), topics, topic_scores, topic_sources,
                         qualities, covered_weight)

    # per-topic breakdown for the SASB materiality-weights panel: every material topic, its
    # weight (as a %), the agency-derived score (None where uncovered), and its contribution.
    topic_breakdown = [{
        "topic_id": t["topic_id"],
        "name": _pretty_topic(t["topic_id"]),
        "pillar": t["pillar"],
        "weight": round(t["weight"] * 100, 1),
        "score": topic_scores.get(t["topic_id"]),
        "contribution": contributions.get(t["topic_id"]),
    } for t in topics]

    return RatingScore(
        company_id=cid, year=year, total=round(score, 1), pillars=pillars,
        coverage=round(covered_weight / total_weight, 3) if total_weight else 0.0,
        contributions=contributions, topic_breakdown=topic_breakdown,
        agencies=sorted(qualities.keys()),
        # every input is real by construction now (real-only agencies + CDP + Climate TRACE),
        # so the rating is "real" whenever it exists — never mixed/illustrative.
        provenance="real", trace=trace,
    )


def _pillar_scores(per_agency_pillars: dict[str, dict[str, float]]) -> dict[str, Optional[float]]:
    """Averaged agency quality per pillar (the E/S/G gauges)."""
    out: dict[str, Optional[float]] = {}
    for p in ("E", "S", "G"):
        vals = [pmap[p] for pmap in per_agency_pillars.values() if p in pmap]
        out[p] = round(sum(vals) / len(vals), 1) if vals else config.NA
    return out


def _build_trace(year, total, topics, topic_scores, topic_sources, qualities, covered_weight) -> TraceNode:
    agency_leaves = [
        leaf(f"{AGENCY_LABEL.get(ch, ch)} → {round(info['quality'], 1)}/100 "
             f"({'real' if info['real'] else 'illustrative'}, {info['year']})",
             f"{AGENCY_LABEL.get(ch, ch)} rating normalized to a 0..100 quality scale.",
             value=info["quality"])
        for ch, info in sorted(qualities.items())
    ]
    topic_nodes = []
    for t in topics:
        ts = topic_scores.get(t["topic_id"])
        if ts is None:
            continue
        contrib = (t["weight"] / covered_weight) * ts
        topic_nodes.append(TraceNode(
            label=f"{t['topic_id']} · pillar {t['pillar']} · w={t['weight']} "
                  f"(from {', '.join(AGENCY_LABEL.get(s, s) for s in topic_sources[t['topic_id']])})",
            value=round(ts, 1), contribution=round(contrib, 2)))
    return TraceNode(
        label=f"ESG rating {year} = SASB-weighted agency consensus", value=total,
        children=[TraceNode(label="Agency inputs (normalized 0..100)", value=None,
                            children=agency_leaves),
                  TraceNode(label="Material topics (renormalized over covered weight)",
                            value=None, children=topic_nodes)],
    )


def rating_score(ds: Dataset, cid: str, year: int = config.END_YEAR,
                 pcts: Optional[RaterPercentiles] = None) -> RatingScore:
    """Public entry: the ESG rating for one company-year. `pcts` may be passed in to avoid a
    panel-wide normalization pass (the pipeline already has it)."""
    if pcts is None:
        pcts = normalize_raters(ds, year).get(cid) or RaterPercentiles(company_id=cid)
    return rating_from_pcts(ds, cid, year, pcts)


def rating_series(ds: Dataset, cid: str) -> list[RatingScore]:
    """Per-year ratings (drives the rating trajectory line). Uses each year's own panel
    normalization so a percentile cohort is never borrowed across years."""
    out = []
    for year in config.YEARS:
        pcts = normalize_raters(ds, year).get(cid)
        if pcts is None:
            continue
        rs = rating_from_pcts(ds, cid, year, pcts)
        if rs.total is not None:
            out.append(rs)
    return out
