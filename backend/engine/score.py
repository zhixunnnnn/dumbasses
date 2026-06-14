"""evidence_score — aggregate verified (full) + asserted (partial) claims by SASB weight.

THE T3 INVARIANT lives here. The score is the credit rate over COVERED material weight:

    total = ( Σ_covered weight_t · credit_t ) / ( Σ_covered weight_t )      (×100)

An ABSENT material topic (zero claims) is not in the covered set, so it changes
neither numerator nor denominator -> the score is unchanged. It only lowers
`confidence = (covered_weight / total_material_weight) · mean(verify confidence)`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import config
from .claims import extract_claims
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import EvidenceScore, TraceNode
from .sasb import map_to_sasb, topics_for
from .trace import leaf
from .verify import verify

CREDIT = {"VERIFIED": config.CREDIT_VERIFIED, "ASSERTED": config.CREDIT_ASSERTED}


@dataclass
class TopicAgg:
    topic_id: str
    pillar: str
    weight: float
    credit: float
    verified: int
    asserted: int
    claim_traces: list[TraceNode] = field(default_factory=list)


@dataclass
class ScoreDetail:
    company_id: str
    year: int
    topics: dict[str, TopicAgg]            # covered topics only
    absent_topics: list[str]
    total_material_weight: float
    confidences: list[float]
    verified_count: int


def _aggregate(ds: Dataset, cid: str, year: int, client: LLMClient) -> ScoreDetail:
    comp = ds.company(cid)
    material = {t["topic_id"]: t for t in topics_for(comp.sasb_industry)}
    total_material_weight = sum(t["weight"] for t in material.values())
    company_evidence = ds.evidence_for(cid)

    topics: dict[str, TopicAgg] = {}
    confidences: list[float] = []
    verified_count = 0

    for doc in ds.docs_for(cid, year):
        for claim in extract_claims(doc, client):
            mapping = map_to_sasb(claim, comp.sasb_industry)
            if not mapping.is_material:
                continue
            v = verify(claim, mapping, company_evidence)
            confidences.append(v.confidence)
            if v.state == "VERIFIED":
                verified_count += 1
            agg = topics.get(mapping.topic_id)
            if agg is None:
                agg = TopicAgg(topic_id=mapping.topic_id, pillar=mapping.pillar,
                               weight=mapping.weight, credit=0.0, verified=0, asserted=0)
                topics[mapping.topic_id] = agg
            agg.credit = min(1.0, agg.credit + CREDIT[v.state])
            if v.state == "VERIFIED":
                agg.verified += 1
            else:
                agg.asserted += 1
            agg.claim_traces.append(leaf(
                f"[{v.state}] {claim.text[:90]}", claim.source_sentence,
                doc=claim.source_doc, page=claim.source_page,
                contribution=mapping.weight * CREDIT[v.state],
            ))

    absent = [tid for tid in material if tid not in topics]
    return ScoreDetail(cid, year, topics, absent, total_material_weight, confidences, verified_count)


def _ratio(aggs: list[TopicAgg]) -> Optional[float]:
    w = sum(a.weight for a in aggs)
    if w <= 0:
        return None
    return round(100.0 * sum(a.weight * a.credit for a in aggs) / w, 2)


def evidence_score(ds: Dataset, cid: str, year: int, client: Optional[LLMClient] = None) -> EvidenceScore:
    client = client or MockLLMClient()
    d = _aggregate(ds, cid, year, client)
    covered = list(d.topics.values())

    total = _ratio(covered)
    pillars = {p: _ratio([a for a in covered if a.pillar == p]) for p in ("E", "S", "G")}

    covered_weight = sum(a.weight for a in covered)
    coverage = (covered_weight / d.total_material_weight) if d.total_material_weight else 0.0
    mean_conf = (sum(d.confidences) / len(d.confidences)) if d.confidences else 0.0
    confidence = round(coverage * mean_conf, 3)

    # trace: total -> pillar -> topic -> claim -> source_sentence
    pillar_nodes = []
    for p in ("E", "S", "G"):
        p_aggs = [a for a in covered if a.pillar == p]
        if not p_aggs:
            continue
        topic_nodes = [
            TraceNode(label=f"{a.topic_id} (w={a.weight}, credit={round(a.credit, 2)})",
                      value=round(a.credit * 100, 1), contribution=round(a.weight * a.credit, 3),
                      children=a.claim_traces)
            for a in p_aggs
        ]
        pillar_nodes.append(TraceNode(label=f"Pillar {p}", value=pillars[p], children=topic_nodes))
    trace = TraceNode(label=f"Evidence Score {year}", value=total, children=pillar_nodes)

    return EvidenceScore(company_id=cid, year=year, total=total, pillars=pillars,
                         confidence=confidence, absent_topics=d.absent_topics, trace=trace)


def evidence_series(ds: Dataset, cid: str, client: Optional[LLMClient] = None) -> list[EvidenceScore]:
    """Per-year evidence scores (drives the rising-evidence band and proof_up)."""
    client = client or MockLLMClient()
    out = []
    for year in config.YEARS:
        if ds.docs_for(cid, year):
            out.append(evidence_score(ds, cid, year, client))
    return out


def verified_count(ds: Dataset, cid: str, year: int, client: Optional[LLMClient] = None) -> int:
    return _aggregate(ds, cid, year, client or MockLLMClient()).verified_count


def claim_table(ds: Dataset, cid: str, year: int, client: Optional[LLMClient] = None) -> dict:
    """Claims grouped for the UI, plus the ABSENT material topics (shown but not scored)."""
    d = _aggregate(ds, cid, year, client or MockLLMClient())
    rows = []
    for agg in d.topics.values():
        for node in agg.claim_traces:
            state = node.label.split("]")[0].lstrip("[") if node.label.startswith("[") else "ASSERTED"
            rows.append({
                "topic_id": agg.topic_id, "pillar": agg.pillar, "state": state,
                "text": node.label.split("] ", 1)[-1], "source_sentence": node.source_sentence,
                "source_doc": node.source_doc, "source_page": node.source_page,
                "weight": agg.weight,
            })
    absent = [{"topic_id": t, "state": "ABSENT"} for t in d.absent_topics]
    return {"claims": rows, "absent": absent}
