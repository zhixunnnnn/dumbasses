"""map_to_sasb — tag a claim to a material SASB topic for the company's industry.

Deterministic keyword matching against `sasb_materiality.json` (the only place
weights live). Non-material claims get weight 0 (a note), never material credit.
"""
from __future__ import annotations

import functools

from . import config
from .models import Claim, SASBMapping


@functools.lru_cache(maxsize=1)
def _materiality() -> dict:
    return config.load_json("sasb_materiality.json")


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
