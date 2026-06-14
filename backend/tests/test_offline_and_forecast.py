"""T4 (offline: zero network) and T8 (forecast explainability)."""
from __future__ import annotations

import socket

from backend.engine import ingest, predict
from backend.engine.llm import MockLLMClient, get_default_client


# --- T4: the full pipeline runs with ZERO network calls ------------------------
def test_T4_offline_zero_network(monkeypatch, tmp_path):
    def _blocked(*a, **k):
        raise AssertionError("network call attempted during --offline run")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    # offline must select the deterministic mock client (never OpenAI)
    assert isinstance(get_default_client(offline=True), MockLLMClient)

    from backend.engine import pipeline
    summary = pipeline.build(offline=True, retrain=True)   # full pipeline + JSON dump
    assert summary["companies"] == 10


# --- T8: forecast is explainable, honest, and non-circular ---------------------
def test_T8_forecast_explainable_and_non_circular():
    ds = ingest.load()
    model = predict.train(ds, MockLLMClient())
    fc = predict.forecast(ds, "U96", model, MockLLMClient())

    assert fc.predicted_score is not None
    assert fc.feature_contributions, "no feature attribution"
    assert fc.val_error is not None, "validation error not reported"
    assert fc.hypothesis is True, "forecast must be HYPOTHESIS-labelled"

    # non-circular: the lagged ESG/evidence score is NOT a feature
    banned = ("evidence", "esg", "score", "total")
    assert not any(any(b in f.lower() for b in banned) for f in predict.FEATURES)
    assert not any(any(b in fc_.feature.lower() for b in banned) for fc_ in fc.feature_contributions)
