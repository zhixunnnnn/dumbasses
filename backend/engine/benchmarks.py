"""Industry benchmarks — what "normal" looks like for a SASB industry.

Three layers, honest about which one you are reading:
  * computed — the median evidence score of the real companies judged on that rubric. Free
    and always current, but a median over two names is not an authoritative industry norm,
    so the SOURCE LABEL always carries the peer count ("panel median (n=3)") and flags a
    cohort below MIN_PEERS_FOR_SECTOR_RANK. The label is what stops a thin median from
    reading as a real bar — not hiding the number.
  * modelled baseline — a stable sector-shaped fallback used when the demo universe has
    no scored company for that industry. It is labelled in the API/UI and never replaces
    a panel median or override.
  * override — a hand-entered figure (e.g. a published CGSI benchmark) stored in
    `industry_benchmarks`, which always wins when present and is always labelled as the
    override.

With config.ALLOW_ILLUSTRATIVE_FALLBACK off, unavailable or undersized cohorts remain
N.A. with no source.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Optional

from . import config, ingest
from .db import bootstrap
from .ingest import Dataset
from .llm import LLMClient
from .sasb import known_industries
from .score import evidence_score

METRICS = ("total", "E", "S", "G")
COMPUTED_SOURCE = "panel median"      # source label shown when no override is stored
MODELLED_SOURCE = "modelled baseline"

# Stable demo baselines keep the settings panel useful beyond the currently scored utility
# universe. Pillars are sector-shaped and totals are their rounded mean; they are fallbacks,
# not published measurements.
MODELLED_BASELINES: dict[str, dict[str, float]] = {
    "Commercial Banks": {"total": 68.1, "E": 64.2, "S": 67.8, "G": 72.4},
    "Real Estate": {"total": 64.5, "E": 61.5, "S": 63.8, "G": 68.1},
    "Electric Utilities & Power Generators": {
        "total": 64.4, "E": 58.6, "S": 65.2, "G": 69.4,
    },
    "Airlines": {"total": 60.7, "E": 52.4, "S": 66.1, "G": 63.7},
    "Agricultural Products": {"total": 63.9, "E": 62.7, "S": 67.3, "G": 61.8},
    "Telecommunication Services": {"total": 69.2, "E": 65.8, "S": 71.6, "G": 70.2},
}


def _panel_medians(ds: Dataset, client: Optional[LLMClient] = None
                   ) -> dict[str, dict[str, tuple[Optional[float], int]]]:
    """{industry: {metric: (median, n_companies)}}. None values are skipped rather than
    counted as zeros, so a company we have no evidence for does not drag the median down —
    which also means n is the count that ACTUALLY backs this metric, not the industry size."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for comp in ds.companies.values():
        es = evidence_score(ds, comp.company_id, config.END_YEAR, client)
        values = {"total": es.total, **{p: es.pillars.get(p) for p in ("E", "S", "G")}}
        bucket = buckets.setdefault(comp.sasb_industry, {m: [] for m in METRICS})
        for metric, value in values.items():
            if value is not None:
                bucket[metric].append(float(value))
    return {
        industry: {m: ((round(median(vals), 2) if vals else config.NA), len(vals))
                   for m, vals in bucket.items()}
        for industry, bucket in buckets.items()
    }


def computed_benchmarks(ds: Dataset, client: Optional[LLMClient] = None
                        ) -> dict[str, dict[str, Optional[float]]]:
    """Median evidence score (total + per pillar) per sasb_industry across the panel.

    Thin cohorts are NOT suppressed here — `benchmark_source` labels them instead — except
    in strict mode (config.ALLOW_ILLUSTRATIVE_FALLBACK off), where a median below the peer
    floor is N.A. again."""
    return {
        industry: {m: (value if _offerable(value, n) else config.NA)
                   for m, (value, n) in metrics.items()}
        for industry, metrics in _panel_medians(ds, client).items()
    }


def _offerable(value: Optional[float], n: int) -> bool:
    """A median exists at all, and clears the peer floor when strict mode is on."""
    if value is None or n == 0:
        return False
    return config.ALLOW_ILLUSTRATIVE_FALLBACK or n >= config.MIN_PEERS_FOR_SECTOR_RANK


def benchmark_source(n: int) -> str:
    """The source label for a computed median. The peer count always travels with the
    number, and a cohort under the floor says so, so a median over three names can never
    be read as an authoritative industry bar."""
    if n < config.MIN_PEERS_FOR_SECTOR_RANK:
        return f"{COMPUTED_SOURCE} (n={n}, below peer floor)"
    return f"{COMPUTED_SOURCE} (n={n})"


def get_benchmarks(ds: Optional[Dataset] = None) -> list[dict[str, Any]]:
    """One row per (industry, metric): the stored override when there is one, else the
    computed panel median labelled with its peer count, else a labelled modelled baseline
    when demo fallbacks are enabled. `is_override` tells the UI when a stored value wins."""
    if ds is None:
        ds = ingest.load()
    medians = _panel_medians(ds)
    stored = _stored()
    rows = []
    for industry in known_industries():
        for metric in METRICS:
            override = stored.get((industry, metric))
            if override:                       # a published figure always wins, always labelled
                rows.append({
                    "industry": industry, "metric": metric,
                    "value": round(float(override["value"]), 2),
                    "source": override["source"], "updated_at": override["updated_at"],
                    "is_override": True, "peers": None,
                })
                continue
            value, n = medians.get(industry, {}).get(metric, (config.NA, 0))
            offerable = _offerable(value, n)
            modelled = (
                MODELLED_BASELINES.get(industry, {}).get(metric)
                if config.ALLOW_ILLUSTRATIVE_FALLBACK and not offerable
                else None
            )
            rows.append({
                "industry": industry, "metric": metric,
                "value": round(value, 2) if offerable else modelled,
                "source": benchmark_source(n) if offerable else (
                    MODELLED_SOURCE if modelled is not None else config.NA
                ),
                "updated_at": None, "is_override": False, "peers": n,
            })
    return rows


def set_benchmark(industry: str, metric: str, value: float, source: str) -> list[dict[str, Any]]:
    """Store (or replace) an override for one industry/metric."""
    industry = (industry or "").strip()
    metric = (metric or "").strip()
    source = (source or "").strip()
    if industry not in known_industries():
        raise ValueError(f"industry must be one of {', '.join(known_industries())}")
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be a number between 0 and 100") from exc
    if not 0.0 <= value <= 100.0:
        raise ValueError("value must be between 0 and 100")
    if not source:
        raise ValueError("source must not be empty (a benchmark without provenance is a guess)")
    conn = bootstrap()
    try:
        conn.execute(
            """
            INSERT INTO industry_benchmarks (industry, metric, value, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(industry, metric) DO UPDATE SET
                value=excluded.value,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (industry, metric, round(value, 2), source, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_benchmarks()


def delete_benchmark(industry: str, metric: str) -> list[dict[str, Any]]:
    """Drop an override; the row reverts to the computed panel median (labelled with its
    peer count), then the modelled baseline when enabled, then N.A."""
    conn = bootstrap()
    try:
        cur = conn.execute(
            "DELETE FROM industry_benchmarks WHERE industry=? AND metric=?", (industry, metric)
        )
        if not cur.rowcount:
            raise KeyError(f"{industry}/{metric}")
        conn.commit()
    finally:
        conn.close()
    return get_benchmarks()


def _stored() -> dict[tuple[str, str], dict[str, Any]]:
    conn = bootstrap()
    try:
        rows = conn.execute("SELECT * FROM industry_benchmarks").fetchall()
    finally:
        conn.close()
    return {(r["industry"], r["metric"]): dict(r) for r in rows}
