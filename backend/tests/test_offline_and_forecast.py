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
    assert fc.hypothesis is True, "forecast must be HYPOTHESIS-labelled"
    assert fc.model_label, "the forecast must say what produced it"
    # Either a fit with attribution, or the baseline saying so — never a bare number.
    if model.fitted:
        assert fc.feature_contributions, "fitted model gave no feature attribution"
        assert fc.val_error is not None, "validation error not reported"
        assert fc.baseline_only is False
    else:
        assert fc.baseline_only is True
        assert "baseline" in fc.model_label.lower()

    # Non-circular in the sense that matters now: the target is the RATER's rating, so
    # the rating itself must never be a nowcast feature. (The evidence score IS a
    # legitimate input here — it is a different measurement from the rater's opinion.)
    assert "rating_level" not in predict.FEATURES
    assert not any(c.feature == "rating_level" for c in fc.feature_contributions)


# --- the panel is real-only: no row may rest on a seeded or imputed value ------
def test_forecast_panel_rows_are_real():
    ds = ingest.load()
    ratings = predict.real_ratings()
    panel = predict._panel_rows(ds, MockLLMClient(), horizon=0)
    for (cid, year), target in zip(panel.keys, panel.y):
        assert ratings[cid][year] == int(target), "target is not the REAL disclosed rating"
        assert predict._real_evidence_year(cid, year), "feature year has no real report"
