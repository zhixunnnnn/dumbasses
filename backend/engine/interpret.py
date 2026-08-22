"""interpret — why the forecaster produced a given MSCI rating estimate.

The forecaster is a Ridge regression on four standardized features (see predict.py).
For a linear model on standardized inputs the SHAP value of feature *i* is exact and
closed-form — no sampling, no approximation:

    phi_i = coef_i * (z_i - E[z_i]) = coef_i * z_i        (E[z_i] = 0 after scaling)
    base  = intercept_ = E[y]
    prediction = base + sum(phi_i)

So the contributions already computed in `predict.forecast` ARE the SHAP values.
This module surfaces them together with the provenance of each feature's input:
the news feature is traced back to the individual scraped headlines that produced
the sentiment count, and the price features to the weekly close series.

When the panel is too thin to fit (predict.beats_baseline is False) there is no Ridge and
therefore nothing to attribute: the SHAP block reports zero contributions and the model
card says the served number is naive ratings persistence.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import numpy as np

from . import config, ingest
from .llm import get_default_client
from .predict import FEATURES, _real_features, _panel
from .pipeline import _load_or_train
from .predict import _accuracy_block, forecast as run_forecast
from .score import evidence_score

FEATURE_META: dict[str, dict[str, str]] = {
    "news_sentiment": {
        "label": "News sentiment",
        "unit": "positive − controversy headlines",
        "provenance": "dated_news",
        "description": (
            "Net count of LLM-classified headlines PUBLISHED in the row's own year "
            "(GDELT DOC 2.0), positive minus controversy — never back-filled from today."
        ),
    },
    "evidence_total": {
        "label": "Evidence score",
        "unit": "0–100",
        "provenance": "report_claims",
        "description": (
            "That year's evidence score, built from claims extracted from the company's "
            "own report for that year."
        ),
    },
    "price_return": {
        "label": "Price return",
        "unit": "% over the trailing year",
        "provenance": "market_prices",
        "description": (
            "Trailing 1-year return of the weekly close series, clipped at the feature "
            "year so no later price leaks in."
        ),
    },
    "volatility": {
        "label": "Volatility",
        "unit": "% annualised",
        "provenance": "market_prices",
        "description": (
            "Annualised standard deviation of weekly log returns over the same window."
        ),
    },
    "prev_rating_level": {
        "label": "Last known rating",
        "unit": "MSCI level 1–7",
        "provenance": "prior_rating",
        "description": (
            "The company's rating from a STRICTLY EARLIER year — never the year being "
            "predicted. It makes the model a correction to persistence rather than a "
            "guess from scratch, and the evaluation still has to beat persistence."
        ),
    },
}


@lru_cache(maxsize=1)
def _context():
    """Dataset + trained model + LLM client, loaded once per process."""
    client = get_default_client(offline=True)
    dataset = ingest.load()
    model = _load_or_train(dataset, client)
    return dataset, model, client


def reset_cache() -> None:
    _context.cache_clear()


def model_card() -> dict[str, Any]:
    """Global model description: the learned weight on each standardized feature, the
    DIRECTIONAL accuracy with its sample size, and the panel it was fitted on."""
    dataset, model, client = _context()
    X, y, keys = _panel(dataset, client)
    ev = model.evaluation
    coefficients = ([float(v) for v in model.ridge.coef_] if model.ridge is not None
                    else [0.0] * len(FEATURES))
    base_value = float(model.ridge.intercept_) if model.ridge is not None else (
        float(np.mean(y)) if len(y) else 0.0)
    return {
        "modelType": (f"Ridge regression (L2, alpha={ev.alpha}) on standardized features"
                      if model.fitted else "Naive ratings persistence (no fit shipped)"),
        "explainer": "Exact linear SHAP — closed form for a linear model, no sampling",
        "target": ("MSCI ESG rating level (CCC=1 .. AAA=7), same year — REAL disclosed "
                   "letters where a company published one, the illustrative seeded curve "
                   "otherwise, flagged per row"),
        "targetYear": config.CURRENT_YEAR,
        "baseValue": round(base_value, 3),
        "trainingRows": int(len(y)),
        "trainingCompanies": keys,
        "valError": (round(ev.mae, 3) if ev.mae is not None else None),
        "directionalAccuracy": (
            round(model.directional_accuracy, 3)
            if model.directional_accuracy is not None else None
        ),
        "directionalN": model.directional_n,
        # the honesty split: the headline above is measured partly on seeded targets, so
        # the real-target figures ship beside it and are never merged into it
        "accuracyBasis": ("full panel incl. illustrative targets"
                          if model.rows_illustrative else "real targets only"),
        "accuracyNote": _accuracy_block(model)[4],
        "panelRowsReal": model.rows_real,
        "panelRowsIllustrative": model.rows_illustrative,
        "realDirectionalAccuracy": (
            None if model.real_evaluation is None else model.real_evaluation.move_acc),
        "realDirectionalN": (
            None if model.real_evaluation is None else model.real_evaluation.move_n),
        "realMoveBaseline": (
            None if model.real_evaluation is None else model.real_evaluation.move_baseline),
        "realLuckPValue": (
            None if model.real_evaluation is None else model.real_evaluation.p_value),
        "baselineMovePersistence": ev.move_baseline,
        "baselineSide": ev.side_baseline,
        "baselineMaePersistence": ev.baseline_mae_persistence,
        "maeOnPersistenceRows": ev.mae_on_persistence_rows,
        "persistenceN": ev.persistence_n,
        "luckPValue": ev.p_value,
        "fitted": model.fitted,
        "targetMean": (round(float(np.mean(y)), 2) if len(y) else None),
        "targetStd": (round(float(np.std(y)), 2) if len(y) else None),
        "features": [
            {
                "feature": name,
                **FEATURE_META[name],
                "coefficient": round(coefficients[index], 4),
                "mean": round(float(model.means[index]), 4),
                "std": round(float(model.stds[index]), 4),
                # Mean |SHAP| across the panel — the model-wide importance ranking.
                "meanAbsShap": round(
                    float(np.mean(np.abs(
                        coefficients[index]
                        * (X[:, index] - model.means[index]) / model.stds[index])))
                    if len(y) else 0.0,
                    4,
                ),
            }
            for index, name in enumerate(FEATURES)
        ],
        "caveat": (
            "Ratings are sticky, so the figure that matters is DIRECTION, not precision: "
            "the accuracy above is the leave-one-out share of upgrade/hold/downgrade calls "
            "the model got right, with its sample size, against a baseline that always "
            "says hold. With a panel this small an edge over that baseline can be luck — "
            "the p-value says how likely. Read `accuracyNote` before quoting any of it: "
            "the panel is padded with ILLUSTRATIVE (seeded) rating targets so that a fit "
            "is possible at all, so `directionalAccuracy` is NOT a measurement on ratings "
            "anyone published. `realDirectionalAccuracy` is, over `realDirectionalN` rows, "
            "and that is the only figure that may be described as a real result."
        ),
    }


def explain(company_id: str) -> dict[str, Any]:
    """Full prediction explanation for one company: SHAP breakdown, the evidence
    score the model was trained against, and the news items behind the sentiment
    feature."""
    dataset, model, client = _context()
    if company_id not in dataset.companies:
        raise KeyError(company_id)
    company = dataset.company(company_id)
    prediction = run_forecast(dataset, company_id, model, client)
    raw_features = _real_features(dataset, company_id)
    base_value = float(model.ridge.intercept_) if model.ridge is not None else 0.0

    contributions: list[dict[str, Any]] = []
    for index, name in enumerate(FEATURES):
        contribution = next(
            (c for c in prediction.feature_contributions if c.feature == name), None
        )
        raw = raw_features[index] if raw_features else None
        standardized = (
            (raw - float(model.means[index])) / float(model.stds[index])
            if raw is not None
            else None
        )
        contributions.append(
            {
                "feature": name,
                **FEATURE_META[name],
                "rawValue": (round(float(raw), 3) if raw is not None else None),
                "standardizedValue": (
                    round(float(standardized), 3) if standardized is not None else None
                ),
                "coefficient": (round(float(model.ridge.coef_[index]), 4)
                                if model.ridge is not None else 0.0),
                "shap": (round(contribution.contribution, 4) if contribution else 0.0),
                "direction": (
                    "increases"
                    if contribution and contribution.contribution > 0
                    else "decreases"
                    if contribution and contribution.contribution < 0
                    else "neutral"
                ),
            }
        )
    contributions.sort(key=lambda item: -abs(item["shap"]))

    score = evidence_score(dataset, company_id, config.END_YEAR, client)
    return {
        "company": {
            "id": company_id,
            "name": company.name,
            "ticker": company.ticker,
            "sector": company.sector,
            "country": company.country,
            "sasbIndustry": company.sasb_industry,
        },
        "prediction": {
            "predictedScore": prediction.predicted_score,
            "ciLow": prediction.ci_low,
            "ciHigh": prediction.ci_high,
            "targetYear": prediction.target_year,
            "valError": prediction.val_error,
            "directionalAccuracy": prediction.directional_accuracy,
            "directionalN": prediction.directional_n,
            "predictedLabel": prediction.predicted_label,
            "lastRatingLabel": prediction.last_rating_label,
            "lastRatingYear": prediction.last_rating_year,
            "direction": prediction.direction,
            "baselineOnly": prediction.baseline_only,
            "modelLabel": prediction.model_label,
            "hypothesis": prediction.hypothesis,
            "note": prediction.drift_note,
            "unavailableReason": (
                None
                if prediction.predicted_score is not None
                else "No real MSCI rating has been extracted for this company, and the "
                "model has no fitted alternative to fall back on."
            ),
        },
        "shap": {
            "baseValue": round(base_value, 3),
            "sumContributions": round(
                sum(item["shap"] for item in contributions), 3
            ),
            "contributions": contributions,
        },
        "actualEvidence": {
            "year": score.year,
            "total": score.total,
            "pillars": score.pillars,
            "confidence": score.confidence,
            "absentTopics": score.absent_topics,
            "residual": (
                round(prediction.predicted_score - score.total, 2)
                if prediction.predicted_score is not None and score.total is not None
                else None
            ),
        },
        "evidenceTrace": _trace_dict(score.trace),
        "predictionTrace": _trace_dict(prediction.trace),
        "newsEvidence": news_evidence(company_id),
    }


def news_evidence(company_id: str) -> dict[str, Any]:
    """The scraped headline snapshot for this company.

    NOTE: `news_sentiment` is no longer a model feature (GDELT DOC 2.0 covers too few of
    the panel's company-years to use consistently — see predict.FEATURES). These headlines
    are current-day context for a reader, NOT an input the prediction rests on, and the UI
    must not present them as a driver of the number."""
    from .db import bootstrap

    conn = bootstrap()
    try:
        summary = conn.execute(
            "SELECT * FROM news WHERE company_id = ?", (company_id,)
        ).fetchone()
        headlines = conn.execute(
            "SELECT title, url, label, fetched_at FROM news_headlines WHERE company_id = ?",
            (company_id,),
        ).fetchall()
    finally:
        conn.close()

    items = [
        {
            "title": row["title"],
            "url": row["url"],
            "label": row["label"],
            "fetchedAt": row["fetched_at"],
        }
        for row in headlines
    ]
    return {
        "fetchedAt": summary["fetched_at"] if summary else None,
        "itemCount": int(summary["n_items"]) if summary else 0,
        "positive": int(summary["positive"]) if summary else 0,
        "controversy": int(summary["controversy"]) if summary else 0,
        "sentiment": int(summary["sentiment"] or 0) if summary else 0,
        "headlines": items,
        "source": "Bright Data news scrape, labelled by the extraction LLM",
    }


def explain_all() -> list[dict[str, Any]]:
    """One compact row per company for the Interpretability index."""
    dataset, model, client = _context()
    rows: list[dict[str, Any]] = []
    for company_id in dataset.demo_ids():
        company = dataset.company(company_id)
        prediction = run_forecast(dataset, company_id, model, client)
        actual = evidence_score(dataset, company_id, config.END_YEAR, client).total
        top = prediction.feature_contributions[0] if prediction.feature_contributions else None
        rows.append(
            {
                "id": company_id,
                "name": company.name,
                "ticker": company.ticker,
                "sector": company.sector,
                "predictedScore": prediction.predicted_score,
                "ciLow": prediction.ci_low,
                "ciHigh": prediction.ci_high,
                "actualScore": actual,
                "residual": (
                    round(prediction.predicted_score - actual, 2)
                    if prediction.predicted_score is not None and actual is not None
                    else None
                ),
                "topDriver": (
                    {
                        "feature": top.feature,
                        "label": FEATURE_META[top.feature]["label"],
                        "shap": round(top.contribution, 3),
                    }
                    if top
                    else None
                ),
                "contributions": [
                    {
                        "feature": item.feature,
                        "label": FEATURE_META[item.feature]["label"],
                        "shap": round(item.contribution, 3),
                        "rawValue": item.value,
                    }
                    for item in prediction.feature_contributions
                ],
            }
        )
    rows.sort(key=lambda row: -(row["predictedScore"] or -1))
    return rows


def _trace_dict(node: Optional[Any]) -> Optional[dict[str, Any]]:
    if node is None:
        return None
    return {
        "label": node.label,
        "value": node.value,
        "contribution": node.contribution,
        "sourceSentence": node.source_sentence,
        "sourceDoc": node.source_doc,
        "sourcePage": node.source_page,
        "children": [_trace_dict(child) for child in node.children],
    }
