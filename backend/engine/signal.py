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
from .score import evidence_score, evidence_series, verified_count
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


def compute_all(ds: Dataset, client: Optional[LLMClient] = None) -> dict[str, Signal]:
    client = client or MockLLMClient()
    pcts_end = normalize_raters(ds, config.END_YEAR)
    pcts_start = normalize_raters(ds, config.START_YEAR)

    # pass 1: latest evidence score for every company (for the evidence percentile)
    latest: dict[str, EvidenceScore] = {}
    for cid in ds.companies:
        if ds.docs_for(cid, config.END_YEAR):
            latest[cid] = evidence_score(ds, cid, config.END_YEAR, client)
    sector_totals: dict[str, list[float]] = {}
    for cid, es in latest.items():
        if es.total is not None:
            sector_totals.setdefault(ds.company(cid).sector, []).append(es.total)

    signals: dict[str, Signal] = {}
    for cid in ds.demo_ids():
        es = latest.get(cid)
        sector = ds.company(cid).sector
        evidence_pct = (round(_percentile(sector_totals.get(sector, []), es.total), 2)
                        if es and es.total is not None else None)
        cons_end = consensus(pcts_end[cid])
        cons_start = consensus(pcts_start.get(cid)) if cid in pcts_start else None
        div = divergence_index(pcts_end[cid])

        series = evidence_series(ds, cid, client)
        pts = [(e.year, e.total) for e in series if e.total is not None]
        momentum = _slope(pts)
        vcounts = [verified_count(ds, cid, e.year, client) for e in series]
        # proof_up: evidence momentum is rising AND the latest report has
        # independently-VERIFIED support. (We evaluate the latest year directly
        # rather than requiring a monotonic verified-count across years, which
        # would compare incompatible regimes once the latest year is real.)
        latest_verified = vcounts[-1] if vcounts else 0
        proof_up = (momentum is not None and momentum >= config.PROOF_UP_MIN_SLOPE
                    and latest_verified > 0)

        flags = []
        if div is not None:
            flags.append(div >= config.HIGH_DIVERGENCE)
        if cons_start is not None and cons_end is not None:
            flags.append(abs(cons_end - cons_start) < config.STALE_CONSENSUS_EPS)
        opinion_flat = any(flags) if flags else None

        price_flat = price_witness(ds, cid, client).flat.is_flat

        evidence_gap = (round(evidence_pct - cons_end, 2)
                        if evidence_pct is not None and cons_end is not None else None)
        is_uw = is_improver(proof_up, opinion_flat, price_flat)

        trace = TraceNode(label="Underpriced Improver signal", children=[
            TraceNode(label=f"proof_up={proof_up} (evidence momentum {momentum}/yr, verified-driven)",
                      value=momentum, children=[es.trace] if es else []),
            TraceNode(label=f"opinion_flat={opinion_flat} (divergence={div}, consensus {cons_start}->{cons_end})",
                      value=div),
            TraceNode(label=f"price_flat={price_flat} (stock vs STI over the improvement window)"),
            TraceNode(label=f"evidence_gap={evidence_gap} (evidence {evidence_pct} - consensus {cons_end})",
                      value=evidence_gap),
        ])
        signals[cid] = Signal(
            company_id=cid, proof_up=proof_up, opinion_flat=opinion_flat, price_flat=price_flat,
            is_underpriced_improver=is_uw, evidence_gap=evidence_gap, momentum=momentum,
            esg_today=cons_end, quadrant=None, trace=trace)

    # pass 2: quadrant. x split at the consensus-percentile midpoint (principled, not
    # sample-dependent): a company above its sector median rates "high today".
    for s in signals.values():
        if s.momentum is None or s.esg_today is None:
            continue
        x_high = s.esg_today >= config.QUADRANT_X_SPLIT
        y_up = s.momentum > 0
        s.quadrant = (("FUTURE_LEADERS" if x_high else "HIDDEN_WINNERS") if y_up
                      else ("OVERRATED" if x_high else "VALUE_TRAPS"))
    return signals


def signal(ds: Dataset, cid: str, client: Optional[LLMClient] = None) -> Signal:
    return compute_all(ds, client)[cid]
