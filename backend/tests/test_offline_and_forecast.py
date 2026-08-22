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


# --- every FEATURE is real; the TARGET may be seeded, but only when it says so ----
def test_forecast_panel_features_are_real_and_targets_are_labelled():
    """The panel is padded with illustrative rating targets so the model can fit at all
    (config.ALLOW_ILLUSTRATIVE_FALLBACK). The features are never padded, and every row
    knows which kind of target it carries."""
    ds = ingest.load()
    ratings = predict.real_ratings()
    panel = predict._panel_rows(ds, MockLLMClient(), horizon=0)
    assert len(panel.target_is_real) == len(panel), "a row shipped without a target flag"
    for (cid, year), target, is_real in zip(panel.keys, panel.y, panel.target_is_real):
        assert predict._real_evidence_year(cid, year), "feature year has no real report"
        assert is_real == (ratings.get(cid, {}).get(year) is not None), \
            "target_is_real disagrees with the real-ratings store"
        if is_real:
            assert ratings[cid][year] == int(target), "a REAL row is not the disclosed rating"


def test_illustrative_targets_never_pass_as_a_real_accuracy():
    """The deleted "81% accuracy" lie in one test: a model trained with illustrative rows
    must not report a real-target accuracy it did not compute."""
    ds = ingest.load()
    model = predict.train(ds, MockLLMClient())
    acc, n, real_acc, real_n, note = predict._accuracy_block(model)
    if model.rows_illustrative:
        assert "illustrative" in note, "the headline figure hides its illustrative rows"
    if real_acc is None:
        assert "not computed" in note, "a missing real-target accuracy was not disclosed"
        assert real_n is None
    else:
        # it was really computed, on really that many rows, and it is NOT the headline
        # figure copied across
        assert real_n and real_n >= predict.MIN_EVALUABLE_ROWS
        assert real_n == len(model.real_evaluation.preds)
        assert model.real_evaluation.subset == "real"
    for cid in ds.demo_ids():
        fc = predict.forecast(ds, cid, model)
        if fc.real_directional_accuracy is None:
            assert fc.real_directional_n is None, "an n without an accuracy to go with it"
        if fc.directional_accuracy is not None:
            assert fc.accuracy_note and str(fc.directional_n) in fc.accuracy_note
            assert fc.accuracy_basis, "an accuracy shipped without saying what it is over"


def test_forecast_provenance_follows_the_company_own_rating_history():
    """Same real/mixed/illustrative convention as the dashboard: a company whose target
    history is entirely seeded may never be labelled real."""
    ds = ingest.load()
    model = predict.train(ds, MockLLMClient())
    real = predict.real_ratings()
    for cid, label in model.target_provenance.items():
        has_real = bool(real.get(cid))
        assert label in ("real", "mixed", "illustrative")
        assert (label == "illustrative") == (not has_real)
    for cid in ds.demo_ids():
        fc = predict.forecast(ds, cid, model)
        assert fc.provenance == model.target_provenance.get(cid)


def test_the_nowcast_never_sees_the_rating_it_is_predicting():
    """prev_rating_level is a STRICTLY EARLIER year. The contemporaneous rating stays out."""
    assert "rating_level" not in predict.FEATURES
    assert "prev_rating_level" in predict.FEATURES
    ds = ingest.load()
    targets = predict.rating_targets(ds)
    panel = predict._panel_rows(ds, MockLLMClient(), horizon=0)
    idx = panel.features.index("prev_rating_level")
    for (cid, year), prev, row in zip(panel.keys, panel.prev, panel.X):
        assert row[idx] == float(prev), "prev_rating_level is not the row's prior rating"
        earlier = [y for y in targets[cid] if y < year]
        assert earlier and max(earlier) < year, "prev_rating_level came from the target year"
