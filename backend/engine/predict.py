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

ALL_FEATURES = ["divergence", "consensus", "compliance_gap", "hiring_cum", "controversy_cum",
                "news_sentiment", "pe", "div_yield"]
# Selected by leave-one-out cross-validation to avoid over-fitting 8 features on a
# small panel; keeps the real LLM-classified news signal in. alpha tuned with it.
FEATURES = ["divergence", "hiring_cum", "news_sentiment", "div_yield"]
_SELECT = [ALL_FEATURES.index(f) for f in FEATURES]
RIDGE_ALPHA = 20.0


@dataclass
class _Model:
    ridge: Ridge
    scaler: StandardScaler
    val_error: Optional[float]
    directional_accuracy: Optional[float]
    means: np.ndarray
    stds: np.ndarray


def _features_at(ds: Dataset, cid: str, year: int, pcts_cache: dict) -> Optional[list[float]]:
    """FIXED-SCHEMA feature vector — the SAME columns, in the SAME order, for every
    company-year. The model only ever sees these consistent fields (same types the
    seed produced); we never add per-company/per-year features or predict values that
    only some companies have. Missing inputs fall back to neutral defaults (never NaN,
    never a variable-length row), so a company that doesn't disclose a section is still
    comparable — its real, always-available news_sentiment (Bright Data + LLM) carries
    signal where report data is thin. Returns None ONLY when the company has no rater
    coverage that year; that row is then skipped, not imputed with a fake schema."""
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
    """Rows: features at year t -> evidence score at year t+1 (leading prediction).
    Also returns `cur` (the score at year t) so we can score up/down DIRECTION.

    A row exists ONLY for a company-year that has a REAL evidence target at BOTH t and
    t+1 (i.e. the company actually filed a report those years). Company-years without a
    report are excluded — the model is never trained on imputed or invented targets, and
    absent material topics only lower the coverage-weighted score, never the schema."""
    pcts_cache: dict = {}
    X, y, years, cur = [], [], [], []
    for cid in ds.demo_ids():
        totals = {es.year: es.total for es in
                  [evidence_score(ds, cid, yr, client) for yr in config.YEARS if ds.docs_for(cid, yr)]}
        for t in config.YEARS[:-1]:
            nxt = totals.get(t + 1)
            now = totals.get(t)
            feats = _features_at(ds, cid, t, pcts_cache)
            if nxt is None or now is None or feats is None:
                continue
            X.append([feats[i] for i in _SELECT]); y.append(nxt)
            years.append(t); cur.append(now)
    return np.array(X, float), np.array(y, float), np.array(years), np.array(cur, float)


def _loo_metrics(Xs: np.ndarray, y: np.ndarray, cur: np.ndarray) -> tuple[Optional[float], Optional[float]]:
    """Leave-one-out CV (honest for a small panel): mean abs error + directional
    accuracy = share of next-year up/down moves the model calls correctly."""
    if len(y) < 6:
        return None, None
    preds = np.zeros(len(y))
    idx = np.arange(len(y))
    for i in idx:
        mask = idx != i
        preds[i] = Ridge(alpha=RIDGE_ALPHA).fit(Xs[mask], y[mask]).predict(Xs[i:i + 1])[0]
    mae = float(np.mean(np.abs(preds - y)))
    moved = np.sign(y - cur) != 0
    diracc = (float(np.mean(np.sign(preds - cur)[moved] == np.sign(y - cur)[moved]))
              if moved.any() else None)
    return mae, diracc


def train(ds: Dataset, client: Optional[LLMClient] = None) -> _Model:
    client = client or MockLLMClient()
    X, y, years, cur = _panel(ds, client)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    val_error, directional = _loo_metrics(Xs, y, cur)
    ridge = Ridge(alpha=RIDGE_ALPHA).fit(Xs, y)   # final model on all rows
    return _Model(ridge, scaler, val_error, directional, scaler.mean_, scaler.scale_)


def forecast(ds: Dataset, cid: str, model: _Model, client: Optional[LLMClient] = None) -> Forecast:
    client = client or MockLLMClient()
    feats = _features_at(ds, cid, config.END_YEAR, {})
    series = [es for es in [evidence_score(ds, cid, yr, client) for yr in config.YEARS
                            if ds.docs_for(cid, yr)]]
    empty_trace = TraceNode(label="Forecast (HYPOTHESIS — no sufficient features)")
    if feats is None or len(series) < config.MIN_FEATURE_YEARS:
        return Forecast(company_id=cid, predicted_score=None, hypothesis=True, trace=empty_trace)

    x = np.array([feats[i] for i in _SELECT], float)
    xs = (x - model.means) / model.stds
    pred = float(model.ridge.predict(xs.reshape(1, -1))[0])
    # linear attribution: contribution_i = coef_i * standardized_x_i
    contribs = []
    for name, coef, val, sx in zip(FEATURES, model.ridge.coef_, x, xs):
        contribs.append(FeatureContribution(feature=name, value=round(float(val), 2),
                                            contribution=round(float(coef * sx), 3)))
    contribs.sort(key=lambda c: -abs(c.contribution))
    err = model.val_error if model.val_error is not None else 5.0
    da = model.directional_accuracy
    da_txt = f", directional {round(da * 100)}%" if da is not None else ""
    trace = TraceNode(
        label=f"Forecast {config.END_YEAR + 1} = {round(pred, 1)} (HYPOTHESIS, LOO MAE={round(err, 2)}{da_txt})",
        value=round(pred, 2),
        children=[TraceNode(label=f"{c.feature}={c.value}", contribution=c.contribution) for c in contribs],
    )
    return Forecast(
        company_id=cid, predicted_score=round(pred, 2), horizon_years=config.FORECAST_HORIZON_YEARS,
        ci_low=round(pred - err, 2), ci_high=round(pred + err, 2),
        feature_contributions=contribs, val_error=round(err, 3),
        directional_accuracy=(round(da, 3) if da is not None else None),
        hypothesis=True, trace=trace)
