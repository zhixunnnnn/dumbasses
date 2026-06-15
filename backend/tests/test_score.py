"""T1 (trace integrity, evidence layer) and T3 (coverage-weighted absence)."""
from __future__ import annotations

import json

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


def test_T3_absence_lowers_score(_patched_materiality):
    # Coverage-weighted scoring: undisclosed material topics now count as zeros in
    # the denominator, so they pull the score DOWN (no longer isolated to confidence).
    # A: 6 material topics (4 ABSENT, total weight 1.0). B: same 2 covered claims,
    # only 2 material topics (0 absent, total weight 0.5).
    # numerator = alpha VERIFIED 0.30*1.0 + bravo ASSERTED 0.20*0.5 = 0.40
    a = evidence_score(_build("AA", "X6"), "AA", 2023, client=None)
    b = evidence_score(_build("BB", "X2"), "BB", 2023, client=None)
    assert a.total == 40.0, "0.40 / 1.0 total material weight"
    assert b.total == 80.0, "0.40 / 0.5 total material weight"
    assert a.total < b.total, "undisclosed material topics should lower the score"
    assert a.confidence < b.confidence, "absence also lowers confidence"
    assert set(a.absent_topics) == {"charlie", "delta", "echo", "foxtrot"}
    assert b.absent_topics == []


def test_latest_score_prefers_live_report_claim_cache(_patched_materiality, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    cache_dir = tmp_path / "realclaims"
    cache_dir.mkdir()
    (cache_dir / "AA.json").write_text(
        json.dumps(
            {
                "source_url": "https://example.com/live-report.pdf",
                "source_title": "Live Report",
                "rows": [
                    {
                        "topic_id": "bravo",
                        "pillar": "G",
                        "state": "ASSERTED",
                        "text": "Live report improved bravo controls.",
                        "source_sentence": "Live report improved bravo controls.",
                        "source_doc": "Live Report",
                        "source_page": 4,
                        "weight": 0.2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    score = evidence_score(_build("AA", "X2"), "AA", config.END_YEAR, client=None)

    # coverage-weighted: bravo ASSERTED 0.20*0.5 = 0.10 over total material weight 0.50 = 20.0
    assert score.total == 20.0
    assert score.absent_topics == ["alpha"]
    assert score.trace.children[0].children[0].children[0].source_doc == "Live Report"
