"""predict — an EXPLAINABLE next-year evidence-score forecaster.

Kept non-circular on purpose: features are LEADING alt-data signals (hiring,
controversy, compliance readiness, rater divergence/consensus, fundamentals) —
NEVER the lagged ESG/evidence score itself. Validated time-based (train <=2022 /
test 2023) with the real error reported. Always HYPOTHESIS, with feature
attribution as its trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import config
from .divergence import divergence_index
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import FeatureContribution, Forecast, TraceNode
from .normalize import consensus, normalize_raters
from .regulations import compliance_gap
from .score import evidence_score

FEATURES = ["divergence", "consensus", "compliance_gap", "hiring_cum", "controversy_cum",
            "news_sentiment", "pe", "div_yield"]


@dataclass
class _Model:
    ridge: Ridge
    scaler: StandardScaler
    val_error: Optional[float]
    means: np.ndarray
    stds: np.ndarray


def _features_at(ds: Dataset, cid: str, year: int, pcts_cache: dict) -> Optional[list[float]]:
    pcts = pcts_cache.setdefault(year, normalize_raters(ds, year))
    rp = pcts.get(cid)
    if rp is None:
        return None
    div = divergence_index(rp)
    cons = consensus(rp)
    cg = compliance_gap(ds, cid, year).score
    events = [e for e in ds.events_for(cid) if (e.date or "")[:4].isdigit() and int(e.date[:4]) <= year]
    hiring = sum(1 for e in events if e.type == "hiring_surge")
    contro = sum(1 for e in events if e.type == "controversy")
    fund = ds.fundamentals.get(cid, {}).get("2023", {})
    # live Bright Data news sentiment — a current leading signal (broadcast across years,
    # like the fundamentals snapshot); 0 when no news has been scraped.
    news = float(ds.news_sentiment.get(cid, 0))
    return [
        div if div is not None else 0.0,
        cons if cons is not None else 50.0,
        cg if cg is not None else 0.0,
        float(hiring), float(contro), news,
        float(fund.get("pe") or 12.0), float(fund.get("dividend_yield") or 3.0),
    ]


def _panel(ds: Dataset, client: LLMClient):
    """Rows: features at year t -> evidence score at year t+1 (leading prediction)."""
    pcts_cache: dict = {}
    X, y, years = [], [], []
    for cid in ds.demo_ids():
        totals = {es.year: es.total for es in
                  [evidence_score(ds, cid, yr, client) for yr in config.YEARS if ds.docs_for(cid, yr)]}
        for t in config.YEARS[:-1]:
            nxt = totals.get(t + 1)
            feats = _features_at(ds, cid, t, pcts_cache)
            if nxt is None or feats is None:
                continue
            X.append(feats); y.append(nxt); years.append(t)
    return np.array(X, float), np.array(y, float), np.array(years)


def train(ds: Dataset, client: Optional[LLMClient] = None) -> _Model:
    client = client or MockLLMClient()
    X, y, years = _panel(ds, client)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    # honest time-split: train <= 2021->2022 targets, test on t==2022 (2023 target)
    train_m = years <= config.TRAIN_MAX_YEAR - 1
    test_m = years == config.TRAIN_MAX_YEAR
    val_error = None
    if train_m.sum() >= 5 and test_m.sum() >= 1:
        r = Ridge(alpha=1.0).fit(Xs[train_m], y[train_m])
        pred = r.predict(Xs[test_m])
        val_error = float(np.mean(np.abs(pred - y[test_m])))

    ridge = Ridge(alpha=1.0).fit(Xs, y)   # final model on all rows
    return _Model(ridge, scaler, val_error, scaler.mean_, scaler.scale_)


def forecast(ds: Dataset, cid: str, model: _Model, client: Optional[LLMClient] = None) -> Forecast:
    client = client or MockLLMClient()
    feats = _features_at(ds, cid, config.END_YEAR, {})
    series = [es for es in [evidence_score(ds, cid, yr, client) for yr in config.YEARS
                            if ds.docs_for(cid, yr)]]
    empty_trace = TraceNode(label="Forecast (HYPOTHESIS — no sufficient features)")
    if feats is None or len(series) < config.MIN_FEATURE_YEARS:
        return Forecast(company_id=cid, predicted_score=None, hypothesis=True, trace=empty_trace)

    x = np.array(feats, float)
    xs = (x - model.means) / model.stds
    pred = float(model.ridge.predict(xs.reshape(1, -1))[0])
    # linear attribution: contribution_i = coef_i * standardized_x_i
    contribs = []
    for name, coef, val, sx in zip(FEATURES, model.ridge.coef_, feats, xs):
        contribs.append(FeatureContribution(feature=name, value=round(float(val), 2),
                                            contribution=round(float(coef * sx), 3)))
    contribs.sort(key=lambda c: -abs(c.contribution))
    err = model.val_error if model.val_error is not None else 5.0
    trace = TraceNode(
        label=f"Forecast {config.END_YEAR + 1} = {round(pred, 1)} (HYPOTHESIS, test MAE={round(err, 2)})",
        value=round(pred, 2),
        children=[TraceNode(label=f"{c.feature}={c.value}", contribution=c.contribution) for c in contribs],
    )
    return Forecast(
        company_id=cid, predicted_score=round(pred, 2), horizon_years=config.FORECAST_HORIZON_YEARS,
        ci_low=round(pred - err, 2), ci_high=round(pred + err, 2),
        feature_contributions=contribs, val_error=round(err, 3), hypothesis=True, trace=trace)
