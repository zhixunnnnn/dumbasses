"""map_to_sasb — tag a claim to a material SASB topic for the company's industry.

Deterministic keyword matching against `sasb_materiality.json` (the only place
weights live). Non-material claims get weight 0 (a note), never material credit.
"""
from __future__ import annotations

import functools
import logging

from . import config
from .models import Claim, SASBMapping

logger = logging.getLogger(__name__)

# keys in sasb_materiality.json that are not industries
NON_INDUSTRY_KEYS = ("_comment", "Default")


@functools.lru_cache(maxsize=1)
def _materiality() -> dict:
    return config.load_json("sasb_materiality.json")


def known_industries() -> list[str]:
    """Industries with a real rubric (excludes the file comment and the generic Default)."""
    return [k for k in _materiality() if k not in NON_INDUSTRY_KEYS]


def warn_unmapped_industries(companies) -> dict[str, list[str]]:
    """topics_for() falls back to Default silently, so an industry string with no rubric
    would be scored on a generic one with nothing in the trace to say so. Log it loudly
    instead — but do not hard-fail: reference data legitimately lands before the rubric."""
    known = set(_materiality())          # "Default" is an explicit choice, not a silent fallback
    unmapped: dict[str, list[str]] = {}
    for comp in companies:
        industry = comp.sasb_industry
        if industry and industry not in known:
            unmapped.setdefault(industry, []).append(comp.company_id)
    for industry, cids in unmapped.items():
        logger.warning(
            "SASB industry %r has no rubric in sasb_materiality.json — %d company(ies) "
            "(%s) will be scored on the generic Default rubric.",
            industry, len(cids), ", ".join(sorted(cids)),
        )
    return unmapped


def topics_for(industry: str) -> list[dict]:
    mat = _materiality()
    block = mat.get(industry) or mat["Default"]
    return block["topics"]


def map_to_sasb(claim: Claim, industry: str) -> SASBMapping:
    text = claim.text.lower()
    best, best_hits = None, 0
    for t in topics_for(industry):
        hits = sum(1 for kw in t["keywords"] if kw.lower() in text)
        if hits > best_hits:
            best, best_hits = t, hits
    if best is None:
        return SASBMapping(claim_id=claim.id, topic_id="non_material", pillar="G",
                           is_material=False, weight=0.0, domain="governance")
    return SASBMapping(claim_id=claim.id, topic_id=best["topic_id"], pillar=best["pillar"],
                       is_material=True, weight=float(best["weight"]), domain=best["domain"])
