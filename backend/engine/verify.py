"""verify — route a claim to the most authoritative source for its domain and assign a state.

Returns VERIFIED or ASSERTED only. The third state ABSENT is *topic-level* and is
derived in score.py (a material topic with zero claims).

Critical rules (build-spec §4.3):
  * Asymmetric specialist rule: a specialist source (CDP, EcoVadis) that SUPPORTS the
    claim raises it to VERIFIED. A specialist that is ABSENT changes nothing — never a penalty.
  * Contradicting evidence -> stays ASSERTED with low confidence + a controversy flag
    (we never add a 4th "false" state; controversy is a separate channel).
"""
from __future__ import annotations

import functools
from typing import Optional

from . import config
from .ingest import EvidenceRow
from .models import EvidenceRef, SASBMapping, Verification


@functools.lru_cache(maxsize=1)
def _authority() -> dict:
    return config.load_json("source_authority.json")["domains"]


def _is_specialist(domain: str) -> bool:
    return bool(_authority().get(domain, {}).get("specialist"))


def verify(claim, mapping: SASBMapping, company_evidence: list[EvidenceRow]) -> Verification:
    domain = mapping.domain
    # match evidence by domain + (topic or untagged) + same reporting year
    relevant = [
        e for e in company_evidence
        if e.domain == domain
        and (e.topic_id in (None, mapping.topic_id))
        and (e.date or "").startswith(str(claim.year))
    ]
    supporting = [e for e in relevant if e.supports]
    contradicting = [e for e in relevant if not e.supports]

    refs = [EvidenceRef(authority_source=e.authority_source, snippet=e.snippet,
                        url=e.url, supports=e.supports) for e in relevant]

    if supporting:
        conf = 0.9 if _is_specialist(domain) else 0.75
        return Verification(claim_id=claim.id, state="VERIFIED", evidence_refs=refs,
                            confidence=conf, authority_source=supporting[0].authority_source)
    if contradicting:
        return Verification(claim_id=claim.id, state="ASSERTED", evidence_refs=refs,
                            confidence=0.2, authority_source=contradicting[0].authority_source,
                            controversy=True)
    # asserted: company states it, no external corroboration found -> NOT penalized
    return Verification(claim_id=claim.id, state="ASSERTED", evidence_refs=[], confidence=0.4)
