"""compliance_gap — per-company disclosure compliance against SG/ASEAN regimes.

The effective-year gate is the trap: a regulation NOT yet in force in a reporting
year is NA / "readiness gap", never a violation (T9). Unknown status = excluded
from the denominator, never counted as MISSING.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

from . import config
from .ingest import Dataset
from .models import ComplianceGap, RegStatus, TraceNode
from .trace import leaf

_SENT = re.compile(r"(?<=[.!?])\s+")
_RANK = {"MISSING": 0, "PARTIAL": 1, "MET": 2}   # compliance ordering


@functools.lru_cache(maxsize=1)
def _reg_keywords() -> dict[str, list[str]]:
    regs = config.load_json("regulations.json")["regulations"]
    return {r["reg_id"]: r.get("disclosure_keywords", []) for r in regs}


@functools.lru_cache(maxsize=1)
def _reg_sectors() -> dict[str, list[str]]:
    """reg_id -> the sectors a regulation specifically targets (config-driven, auditable).
    Empty/absent means the regulation is not sector-restricted (falls back to scope)."""
    regs = config.load_json("regulations.json")["regulations"]
    return {r["reg_id"]: r.get("applies_to_sectors", []) for r in regs}


def _applicable(reg, sector: str, is_fi: bool, is_sgx: bool, is_asean: bool) -> bool:
    # A sector-targeted regulation (e.g. SGX climate's phased rollout) binds only the
    # sectors it names; otherwise fall back to the jurisdiction/who-it-binds scope.
    sectors = _reg_sectors().get(reg.reg_id) or []
    if sectors:
        return sector in sectors
    if reg.scope == "MAS-FI":
        return is_fi
    if reg.scope.startswith("SGX"):
        return is_sgx
    if reg.scope.startswith("ASEAN"):
        return is_asean
    return True


def _disclosure_sentence(ds: Dataset, cid: str, year: int, keywords: list[str]) -> Optional[str]:
    docs = ds.docs_for(cid, year) or ds.docs_for(cid)
    if not docs:
        return None
    sentences = [s.strip() for s in _SENT.split(docs[0].text) if s.strip()]
    for s in sentences:
        low = s.lower()
        if any(kw.lower() in low for kw in keywords):
            return s
    return sentences[0] if sentences else None   # fall back to a real report sentence


def compliance_gap(ds: Dataset, cid: str, year: int = config.END_YEAR) -> ComplianceGap:
    comp = ds.company(cid)
    is_fi = comp.sasb_industry == "Commercial Banks"
    is_sgx = comp.country == "Singapore"
    is_asean = True
    kw = _reg_keywords()
    comp_rows = {(r.reg_id): r for r in ds.compliance_for(cid) if r.year == year}

    met: list[RegStatus] = []
    partial: list[RegStatus] = []
    missing: list[RegStatus] = []
    not_in_force: list[RegStatus] = []
    children: list[TraceNode] = []

    for reg in ds.regulations:
        if not _applicable(reg, comp.sector, is_fi, is_sgx, is_asean):
            continue
        rs = RegStatus(reg_id=reg.reg_id, name=reg.name, status="NA")
        if year < reg.effective_year:
            rs.status = "NA"
            not_in_force.append(rs)
            children.append(TraceNode(label=f"{reg.name} — not yet in force ({reg.effective_year})"))
            continue

        # Combine the deterministic seed status with LIVE scraped evidence (real
        # source link + verbatim excerpt). Snippet-level evidence can CONFIRM or
        # UPGRADE a company but must never downgrade it on a thin snippet, so the
        # displayed status is the BETTER of the two; the scraped proof is attached
        # whenever a real source was found. No scraped MISSING (snippet absence is
        # not proof of non-compliance) — MISSING only comes from the curated seed.
        row = comp_rows.get(reg.reg_id)
        seed_status = row.status if row else None
        ev = ds.reg_evidence_for(cid, reg.reg_id) if year == config.END_YEAR else None
        ev_status = ev.status if ev else None
        ranked = [s for s in (seed_status, ev_status) if s in _RANK]
        status = max(ranked, key=_RANK.__getitem__) if ranked else None
        proof = ev if (ev and ev.source_url) else None

        if status in ("MET", "PARTIAL"):
            upd = {"status": status}
            if proof:
                upd.update(scraped=True, source_url=proof.source_url, source_excerpt=proof.source_excerpt)
                children.append(leaf(f"{reg.name} — {status} (live)",
                                     proof.source_excerpt or reg.requirement, doc=proof.source_url))
            else:
                sent = _disclosure_sentence(ds, cid, year, kw.get(reg.reg_id, []))
                children.append(leaf(f"{reg.name} — {status}", sent or reg.requirement))
            (met if status == "MET" else partial).append(rs.model_copy(update=upd))
        elif status == "MISSING":
            upd = {"status": "MISSING"}
            if proof:
                upd.update(scraped=True, source_url=proof.source_url, source_excerpt=proof.source_excerpt)
            missing.append(rs.model_copy(update=upd))
            children.append(TraceNode(label=f"{reg.name} — MISSING (required, undisclosed)"))
        # status None (unknown) -> excluded entirely (never counted as MISSING)

    denom = len(met) + len(partial) + len(missing)
    score = round(len(missing) / denom, 3) if denom else None
    trace = TraceNode(label="Compliance gap", value=score, children=children)
    return ComplianceGap(company_id=cid, score=score, met=met, partial=partial,
                         missing=missing, not_in_force=not_in_force, trace=trace)
