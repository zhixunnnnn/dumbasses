"""T1 (trace integrity, evidence layer) and T3 (absence isolation)."""
from __future__ import annotations

import pytest

from backend.engine import config, ingest, sasb
from backend.engine.score import evidence_score
from backend.engine.trace import has_source
from backend.tests.conftest import EvidenceRow, make_company, make_dataset
from backend.tests.conftest import DocumentRow

# --- T1 (evidence layer): every demo company's score trace reaches a source sentence
def test_T1_evidence_score_traces_resolve():
    ds = ingest.load()
    for cid in ds.demo_ids():
        for year in config.YEARS:
            if not ds.docs_for(cid, year):
                continue
            es = evidence_score(ds, cid, year)
            assert has_source(es.trace), f"{cid} {year} score has no source sentence"


# --- T3: absence must not move the score, only confidence ----------------------
MAT = {
    "X6": {"topics": [
        {"topic_id": "alpha", "pillar": "E", "weight": 0.30, "domain": "climate", "keywords": ["alpha"]},
        {"topic_id": "bravo", "pillar": "G", "weight": 0.20, "domain": "governance", "keywords": ["bravo"]},
        {"topic_id": "charlie", "pillar": "S", "weight": 0.15, "domain": "labour", "keywords": ["charlie"]},
        {"topic_id": "delta", "pillar": "E", "weight": 0.10, "domain": "climate", "keywords": ["delta"]},
        {"topic_id": "echo", "pillar": "G", "weight": 0.15, "domain": "governance", "keywords": ["echo"]},
        {"topic_id": "foxtrot", "pillar": "S", "weight": 0.10, "domain": "labour", "keywords": ["foxtrot"]},
    ]},
    "X2": {"topics": [
        {"topic_id": "alpha", "pillar": "E", "weight": 0.30, "domain": "climate", "keywords": ["alpha"]},
        {"topic_id": "bravo", "pillar": "G", "weight": 0.20, "domain": "governance", "keywords": ["bravo"]},
    ]},
    "Default": {"topics": [
        {"topic_id": "alpha", "pillar": "E", "weight": 1.0, "domain": "climate", "keywords": ["alpha"]},
    ]},
}

DOC_TEXT = "In 2023 the firm improved alpha metrics strongly. In 2023 the firm improved bravo metrics."


@pytest.fixture
def _patched_materiality(monkeypatch):
    monkeypatch.setattr(sasb, "_materiality", lambda: MAT)
    yield


def _build(cid, industry):
    comp = make_company(cid, sector="Test", industry=industry)
    doc = DocumentRow(cid, f"{cid}-SR2023", f"{cid} SR", 2023, None, 1, DOC_TEXT)
    ev = EvidenceRow(f"{cid}-e", cid, "climate", "CDP", "CDP corroborates alpha",
                     None, True, "2023-12-31", "alpha")  # verifies 'alpha' only
    return make_dataset(companies=[comp], documents=[doc], evidence=[ev])


def test_T3_absence_isolation(_patched_materiality):
    # A: industry with 6 material topics (4 ABSENT). B: same covered claims, only 2 topics (0 absent).
    a = evidence_score(_build("AA", "X6"), "AA", 2023, client=None)
    b = evidence_score(_build("BB", "X2"), "BB", 2023, client=None)
    assert a.total == b.total, "absence moved the SCORE (T3 violation)"
    assert a.confidence < b.confidence, "absence should lower confidence only"
    assert set(a.absent_topics) == {"charlie", "delta", "echo", "foxtrot"}
    assert b.absent_topics == []
