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


@functools.lru_cache(maxsize=1)
def _reg_keywords() -> dict[str, list[str]]:
    regs = config.load_json("regulations.json")["regulations"]
    return {r["reg_id"]: r.get("disclosure_keywords", []) for r in regs}


def _applicable(reg, is_fi: bool, is_sgx: bool, is_asean: bool) -> bool:
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
        if not _applicable(reg, is_fi, is_sgx, is_asean):
            continue
        rs = RegStatus(reg_id=reg.reg_id, name=reg.name, status="NA")
        if year < reg.effective_year:
            rs.status = "NA"
            not_in_force.append(rs)
            children.append(TraceNode(label=f"{reg.name} — not yet in force ({reg.effective_year})"))
            continue
        row = comp_rows.get(reg.reg_id)
        status = row.status if row else None
        if status in ("MET", "PARTIAL"):
            sent = _disclosure_sentence(ds, cid, year, kw.get(reg.reg_id, []))
            node = leaf(f"{reg.name} — {status}", sent or reg.requirement)
            children.append(node)
            (met if status == "MET" else partial).append(rs.model_copy(update={"status": status}))
        elif status == "MISSING":
            missing.append(rs.model_copy(update={"status": "MISSING"}))
            children.append(TraceNode(label=f"{reg.name} — MISSING (required, undisclosed)"))
        # status None (unknown) -> excluded entirely (never counted as MISSING)

    denom = len(met) + len(partial) + len(missing)
    score = round(len(missing) / denom, 3) if denom else None
    trace = TraceNode(label="Compliance gap", value=score, children=children)
    return ComplianceGap(company_id=cid, score=score, met=met, partial=partial,
                         missing=missing, not_in_force=not_in_force, trace=trace)
