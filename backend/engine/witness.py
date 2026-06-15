"""price_witness — assemble the Price Witness: weekly candles + a rising verified-evidence
band + event pins + STI-relative non-reaction. A WITNESS, not an oracle: it shows the gap,
it never claims causation and carries no technical-analysis indicators (build-spec §8).
"""
from __future__ import annotations

import bisect
import datetime as dt
from typing import Optional

from . import config
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import BandSpan, Candle, Witness, WitnessFlat, WitnessPin
from .score import evidence_series, verified_count
from .trace import leaf

_PIN_TYPE = {
    "emissions_verified": "emissions_verified",
    "hiring_surge": "hiring_surge",
    "rater_unchanged": "rater_unchanged",
    "controversy": "controversy",
}


def _snap(date_str: str, fridays: list[str]) -> str:
    if not fridays:
        return date_str
    i = bisect.bisect_left(fridays, date_str)
    cands = [fridays[max(0, i - 1)], fridays[min(len(fridays) - 1, i)]]
    target = dt.date.fromisoformat(date_str)
    return min(cands, key=lambda f: abs((dt.date.fromisoformat(f) - target).days))


def _close_at(candles: list[Candle], date_str: str) -> Optional[float]:
    if not candles:
        return None
    nearest = min(candles, key=lambda c: abs(
        (dt.date.fromisoformat(c.week_date) - dt.date.fromisoformat(date_str)).days))
    return nearest.close


def _anchor(year: int) -> str:
    return f"{year}-12-31"


def price_witness(ds: Dataset, cid: str, client: Optional[LLMClient] = None) -> Witness:
    client = client or MockLLMClient()
    candles = ds.prices.get(cid, [])
    benchmark = ds.prices.get(config.STI_ID, [])
    fridays = [c.week_date for c in candles] or [c.week_date for c in benchmark]

    # --- evidence band: maximal VERIFIED-driven rising spans ---------------------
    series = evidence_series(ds, cid, client)
    yearly = [(es.year, es.total) for es in series if es.total is not None]
    vcount = {es.year: verified_count(ds, cid, es.year, client) for es in series}

    band: list[BandSpan] = []
    i = 0
    while i < len(yearly) - 1:
        j = i
        while (j + 1 < len(yearly) and yearly[j + 1][1] > yearly[j][1]
               and vcount[yearly[j + 1][0]] >= vcount[yearly[j][0]]):   # VERIFIED-driven only
            j += 1
        if j > i:
            (y0, s0), (y1, s1) = yearly[i], yearly[j]
            band.append(BandSpan(
                start_date=_snap(_anchor(y0), fridays), end_date=_snap(_anchor(y1), fridays),
                slope=round((s1 - s0) / (y1 - y0), 2), start_score=s0, end_score=s1))
            i = j
        else:
            i += 1

    # --- non-reaction: stock vs STI over the longest rising span ----------------
    flat = WitnessFlat()
    if band:
        span = max(band, key=lambda b: (
            dt.date.fromisoformat(b.end_date) - dt.date.fromisoformat(b.start_date)).days)
        c0, c1 = _close_at(candles, span.start_date), _close_at(candles, span.end_date)
        b0, b1 = _close_at(benchmark, span.start_date), _close_at(benchmark, span.end_date)
        if c0 and c1 and b0 and b1:
            stock = 100.0 * (c1 / c0 - 1)
            sti = 100.0 * (b1 / b0 - 1)
            rel = stock - sti
            # "not reacted" = the market has NOT bid the stock up vs the benchmark.
            # One-sided on purpose: a stock that LAGGED the market while its evidence
            # rose is the strongest underpriced case, not a disqualifier.
            flat = WitnessFlat(stock_return=round(stock, 2), sti_return=round(sti, 2),
                               rel_return=round(rel, 2), is_flat=(rel <= config.FLAT_BAND))

    # --- pins from the event timeline -------------------------------------------
    pins: list[WitnessPin] = []
    for ev in ds.events_for(cid):
        if ev.type not in _PIN_TYPE:
            continue
        ref = leaf(ev.label, ev.label)  # annotation; richer source attached for emissions below
        if ev.type == "emissions_verified":
            yr = int(ev.date[:4])
            ev_rows = ds.evidence_for(cid, domain="climate", year=yr)
            if ev_rows:
                ref = leaf(ev.label, ev_rows[0].snippet)
        pins.append(WitnessPin(date=_snap(ev.date, fridays), type=_PIN_TYPE[ev.type],
                               label=ev.label, trace_ref=ref))
    # dedupe: a year with several verified climate topics emits one pin, not many
    seen: set = set()
    pins = [p for p in pins if (p.type, p.label) not in seen and not seen.add((p.type, p.label))]
    pins.sort(key=lambda p: p.date)

    return Witness(company_id=cid, candles=candles, band=band, pins=pins,
                   benchmark=benchmark, flat=flat)
