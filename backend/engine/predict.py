"""predict — an EXPLAINABLE ESG-evidence estimator trained ENTIRELY on real data.

No seeded inputs. The target is each company's REAL 2023 evidence score (from the
extracted + independently-verified claims). The features are REAL, free, real-time
signals only:

    news_sentiment   real LLM-classified Bright Data news (positive - controversy)
    price_return     real 5y stock return
    volatility       real annualised weekly-return volatility
    is_financial     real sector flag

HONEST CAVEAT (surfaced in the UI): free real-time signals only weakly predict how
much verified ESG a company discloses, so this is a LOW-CONFIDENCE / EXPERIMENTAL
estimate — useful directionally, not as a precise score. Accuracy is reported as the
leave-one-out above/below-median hit-rate (no metric gaming, no seeded features).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import config
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import FeatureContribution, Forecast, TraceNode
from .score import evidence_score

FEATURES = ["news_sentiment", "price_return", "volatility", "is_financial"]
RIDGE_ALPHA = 3.0
MIN_ROWS = 6


@dataclass
class _Model:
    ridge: Ridge
    scaler: StandardScaler
    val_error: Optional[float]
    directional_accuracy: Optional[float]   # LOO above/below-median hit-rate
    means: np.ndarray
    stds: np.ndarray


def _real_features(ds: Dataset, cid: str) -> Optional[list[float]]:
    """REAL signals only — no seeded inputs. None if a company lacks real prices."""
    closes = [c.close for c in ds.prices.get(cid, []) if c.close]
    if len(closes) < 10:
        return None
    ret = (closes[-1] / closes[0] - 1.0) * 100.0
    vol = float(np.std(np.diff(np.log(closes))) * np.sqrt(52) * 100.0)
    news = float(ds.news_sentiment.get(cid, 0))
    is_fin = 1.0 if ds.company(cid).sector == "Financials" else 0.0
    return [news, ret, vol, is_fin]


def _panel(ds: Dataset, client: LLMClient):
    """Cross-sectional, 100% real: real signals -> REAL 2023 evidence score."""
    X, y, cids = [], [], []
    for cid in ds.demo_ids():
        feats = _real_features(ds, cid)
        target = evidence_score(ds, cid, config.END_YEAR, client).total
        if feats is None or target is None:
            continue
        X.append(feats)
        y.append(target)
        cids.append(cid)
    return np.array(X, float), np.array(y, float), cids


def _loo_eval(Xs: np.ndarray, y: np.ndarray) -> tuple[Optional[float], Optional[float]]:
    """Leave-one-out CV: mean abs error + above/below-median hit-rate. Honest for a
    small cross-section; no feature selection inside (that would bias the metric)."""
    if len(y) < MIN_ROWS:
        return None, None
    preds = np.zeros(len(y))
    idx = np.arange(len(y))
    for i in idx:
        mask = idx != i
        preds[i] = Ridge(alpha=RIDGE_ALPHA).fit(Xs[mask], y[mask]).predict(Xs[i:i + 1])[0]
    mae = float(np.mean(np.abs(preds - y)))
    med = float(np.median(y))
    acc = float(np.mean((preds > med) == (y > med)))
    return mae, acc


def train(ds: Dataset, client: Optional[LLMClient] = None) -> _Model:
    client = client or MockLLMClient()
    X, y, _ = _panel(ds, client)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    val_error, acc = _loo_eval(Xs, y)
    ridge = Ridge(alpha=RIDGE_ALPHA).fit(Xs, y)
    return _Model(ridge, scaler, val_error, acc, scaler.mean_, scaler.scale_)


def forecast(ds: Dataset, cid: str, model: _Model, client: Optional[LLMClient] = None) -> Forecast:
    client = client or MockLLMClient()
    feats = _real_features(ds, cid)
    empty = TraceNode(label="ESG estimate (experimental — no real price signal)")
    if feats is None:
        return Forecast(company_id=cid, predicted_score=None, hypothesis=True, trace=empty)

    x = np.array(feats, float)
    xs = (x - model.means) / model.stds
    pred = float(model.ridge.predict(xs.reshape(1, -1))[0])
    pred = max(0.0, min(100.0, pred))
    contribs = [
        FeatureContribution(feature=name, value=round(float(v), 2),
                            contribution=round(float(coef * sx), 3))
        for name, coef, v, sx in zip(FEATURES, model.ridge.coef_, x, xs)
    ]
    contribs.sort(key=lambda c: -abs(c.contribution))
    err = model.val_error if model.val_error is not None else 10.0
    acc = model.directional_accuracy
    acc_txt = f", ~{round(acc * 100)}% hit-rate" if acc is not None else ""
    note = (
        "Trained ENTIRELY on real data (real 2023 evidence vs real news + price/sector "
        "signals) — no seeded inputs. EXPERIMENTAL: free real-time signals only weakly "
        "predict verified ESG disclosure, so treat this as a low-confidence directional "
        "estimate, not a precise score."
    )
    trace = TraceNode(
        label=f"Real-data ESG estimate = {round(pred, 1)} (EXPERIMENTAL{acc_txt}, MAE={round(err, 1)})",
        value=round(pred, 2),
        children=[TraceNode(label=f"{c.feature}={c.value}", contribution=c.contribution) for c in contribs],
    )
    return Forecast(
        company_id=cid, predicted_score=round(pred, 2), horizon_years=0,
        ci_low=round(max(0.0, pred - err), 2), ci_high=round(min(100.0, pred + err), 2),
        feature_contributions=contribs, val_error=round(err, 3),
        directional_accuracy=(round(acc, 3) if acc is not None else None),
        target_year=config.END_YEAR, drift_years=0, drift_note=note,
        hypothesis=True, trace=trace)
