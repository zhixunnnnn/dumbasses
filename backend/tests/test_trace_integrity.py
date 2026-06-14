"""T1 (full) — every surfaced score/flag/signal resolves through its trace to a
source sentence. The ML forecast is exempt (it is HYPOTHESIS and traces to feature
attribution instead); price/rater legs trace to data rows, but the signal as a whole
embeds the evidence subtree, so it must reach a source sentence.
"""
from __future__ import annotations

from backend.engine import config, ingest
from backend.engine.regulations import compliance_gap
from backend.engine.score import evidence_score
from backend.engine.signal import compute_all
from backend.engine.trace import has_source


def test_T1_every_number_traces_to_a_source_sentence():
    ds = ingest.load()
    sigs = compute_all(ds)
    for cid in ds.demo_ids():
        es = evidence_score(ds, cid, config.END_YEAR)
        assert has_source(es.trace), f"{cid}: evidence score has no source"
        assert has_source(sigs[cid].trace), f"{cid}: signal has no source"
        assert has_source(compliance_gap(ds, cid).trace), f"{cid}: compliance has no source"
