"""signal — the Underpriced Improver. Requires all three legs:

  proof_up      verified evidence trending up over time (VERIFIED-driven, not text volume)
  opinion_flat  raters disagree (high divergence) OR consensus stale over the window
  price_flat    stock has not reacted vs STI over the verified-improvement window

is_underpriced_improver = proof_up AND opinion_flat AND price_flat.
Quadrant: x = ESG-as-the-market-sees-it (rater consensus percentile), y = evidence momentum.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .divergence import divergence_index
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import EvidenceScore, Signal, TraceNode
from .normalize import _percentile, consensus, normalize_raters
from .score import evidence_score, evidence_series, evidenced_count, has_evidence
from .witness import price_witness


def is_improver(proof_up, opinion_flat, price_flat) -> bool:
    """is_underpriced_improver iff ALL three legs are true (T5 truth table)."""
    return bool(proof_up and opinion_flat and price_flat)


def _slope(points: list[tuple[int, float]]) -> Optional[float]:
    if len(points) < config.MIN_YEARS_FOR_MOMENTUM:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom, 3)


def _evidence_population(by_industry, by_sector, panel, comp) -> tuple[list[float], str, int]:
    """The cohort an evidence score may be ranked against.

    An evidence score is `% of THIS company's rubric that it evidenced`, so it is only
    comparable to companies judged on the SAME rubric — i.e. the same `sasb_industry`,
    not the same `sector` (Keppel is Industrials but scored on the utilities rubric).
    Falls back to sector then the whole panel when a cohort is too thin, mirroring
    normalize._population. The basis is returned so the UI can qualify the number; the
    caller must still refuse to rank when even the panel is below the peer floor.
    """
    for pop, basis in ((by_industry.get(comp.sasb_industry, []), comp.sasb_industry),
                       (by_sector.get(comp.sector, []), comp.sector)):
        if len(pop) >= config.MIN_PEERS_FOR_SECTOR_RANK:
            return pop, basis, len(pop)
    return panel, "all companies", len(panel)


def compute_all(ds: Dataset, client: Optional[LLMClient] = None) -> dict[str, Signal]:
    client = client or MockLLMClient()
    pcts_end = normalize_raters(ds, config.END_YEAR)
    pcts_start = normalize_raters(ds, config.START_YEAR)

    # pass 1: latest evidence score for every company (for the evidence percentile)
    latest: dict[str, EvidenceScore] = {}
    for cid in ds.companies:
        if has_evidence(ds, cid, config.END_YEAR):
            latest[cid] = evidence_score(ds, cid, config.END_YEAR, client)
    by_industry: dict[str, list[float]] = {}
    by_sector: dict[str, list[float]] = {}
    panel: list[float] = []
    for cid, es in latest.items():
        if es.total is None:
            continue
        comp = ds.company(cid)
        by_industry.setdefault(comp.sasb_industry, []).append(es.total)
        by_sector.setdefault(comp.sector, []).append(es.total)
        panel.append(es.total)

    signals: dict[str, Signal] = {}
    for cid in ds.demo_ids():
        es = latest.get(cid)
        pop, basis, n_peers = _evidence_population(by_industry, by_sector, panel, ds.company(cid))
        # a rank over fewer than MIN_PEERS_FOR_SECTOR_RANK names in TOTAL is noise, not a
        # percentile — N.A. beats a meaningless number (the basis/peers still ship, so the
        # UI can say why).
        evidence_pct = (round(_percentile(pop, es.total), 2)
                        if es and es.total is not None
                        and len(pop) >= config.MIN_PEERS_FOR_SECTOR_RANK else None)
        cons_end = consensus(pcts_end[cid])
        cons_start = consensus(pcts_start.get(cid)) if cid in pcts_start else None
        div = divergence_index(pcts_end[cid])

        series = evidence_series(ds, cid, client)
        pts = [(e.year, e.total) for e in series if e.total is not None]
        momentum = _slope(pts)
        vcounts = [evidenced_count(ds, cid, e.year, client) for e in series]
        # proof_up: evidence momentum is rising AND the latest report carries
        # evidence (VERIFIED or labelled-INFERRED). We evaluate the latest year
        # directly rather than requiring a monotonic count across years, which
        # would compare incompatible regimes once the latest year is real.
        latest_evidenced = vcounts[-1] if vcounts else 0
        proof_up = (momentum is not None and momentum >= config.PROOF_UP_MIN_SLOPE
                    and latest_evidenced > 0)

        flags = []
        if div is not None:
            flags.append(div >= config.HIGH_DIVERGENCE)
        if cons_start is not None and cons_end is not None:
            flags.append(abs(cons_end - cons_start) < config.STALE_CONSENSUS_EPS)
        opinion_flat = any(flags) if flags else None

        price_flat = price_witness(ds, cid, client).flat.is_flat

        evidence_gap = (round(evidence_pct - cons_end, 2)
                        if evidence_pct is not None and cons_end is not None else None)
        # Everything built on consensus inherits its provenance — the gap is only as real
        # as the weakest half, and that half is always the rater side.
        rater_prov = pcts_end[cid].provenance()
        is_uw = is_improver(proof_up, opinion_flat, price_flat)

        trace = TraceNode(label="Underpriced Improver signal", children=[
            TraceNode(label=f"proof_up={proof_up} (evidence momentum {momentum}/yr, verified-driven)",
                      value=momentum, children=[es.trace] if es else []),
            TraceNode(label=f"opinion_flat={opinion_flat} (divergence={div}, consensus {cons_start}->{cons_end})",
                      value=div),
            TraceNode(label=f"price_flat={price_flat} (stock vs STI over the improvement window)"),
            TraceNode(label=f"evidence_gap={evidence_gap} (evidence {evidence_pct} - consensus {cons_end})",
                      value=evidence_gap,
                      children=[TraceNode(
                          label=f"evidence_pct={evidence_pct} vs {n_peers} companies on the "
                                f"{basis} rubric", value=evidence_pct)]),
        ])
        signals[cid] = Signal(
            company_id=cid, proof_up=proof_up, opinion_flat=opinion_flat, price_flat=price_flat,
            is_underpriced_improver=is_uw, evidence_pct=evidence_pct, evidence_basis=basis,
            evidence_peers=n_peers, evidence_gap=evidence_gap, momentum=momentum,
            esg_today=cons_end, quadrant=None,
            esg_today_provenance=(rater_prov if cons_end is not None else None),
            evidence_gap_provenance=(rater_prov if evidence_gap is not None else None),
            trace=trace)

    # pass 2: quadrant. x split at the consensus-percentile midpoint (principled, not
    # sample-dependent): a company above its sector median rates "high today".
    for s in signals.values():
        if s.momentum is None or s.esg_today is None:
            continue
        x_high = s.esg_today >= config.QUADRANT_X_SPLIT
        y_up = s.momentum > 0
        s.quadrant = (("FUTURE_LEADERS" if x_high else "HIDDEN_WINNERS") if y_up
                      else ("OVERRATED" if x_high else "VALUE_TRAPS"))
        s.quadrant_provenance = s.esg_today_provenance   # x axis IS the consensus
    return signals


def signal(ds: Dataset, cid: str, client: Optional[LLMClient] = None) -> Signal:
    return compute_all(ds, client)[cid]
