"""Orchestrate the engine and precompute the dashboard JSON.

    python -m backend.engine.pipeline            # live LLM if OPENAI_API_KEY set
    python -m backend.engine.pipeline --offline  # demo mode: SQLite + cache + saved model, zero network

Writes backend/out/{companies,matrix,signals}.json and out/company/{id}.json.
"""
from __future__ import annotations

import argparse
import json

import joblib

from . import config, ingest
from .divergence import divergence_index
from .llm import get_default_client
from .normalize import consensus, normalize_raters
from .predict import forecast, train
from .regulations import compliance_gap
from .score import claim_table, evidence_score, evidence_series
from .signal import compute_all
from .witness import price_witness

MODEL_PATH = config.MODELS_DIR / "forecaster.joblib"


def _load_or_train(ds, client, retrain=False):
    if MODEL_PATH.exists() and not retrain:
        return joblib.load(MODEL_PATH)
    model = train(ds, client)
    joblib.dump(model, MODEL_PATH)
    return model


def _dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), "utf-8")


def _company_detail(ds, cid, sig, model, client) -> dict:
    comp = ds.company(cid)
    pcts = normalize_raters(ds, config.END_YEAR)[cid]
    es = evidence_score(ds, cid, config.END_YEAR, client)
    series = [{"year": e.year, "total": e.total, "pillars": e.pillars, "confidence": e.confidence}
              for e in evidence_series(ds, cid, client)]
    fc = forecast(ds, cid, model, client)
    peers = [{"id": c.company_id, "name": c.name,
              "evidence_total": (evidence_score(ds, c.company_id, config.END_YEAR, client).total)}
             for c in ds.companies.values()
             if c.scope == "demo" and c.sector == comp.sector and c.company_id != cid]
    return {
        "company": comp.model_dump(),
        "evidence": es.model_dump(),
        "series": series,
        "raters": {**pcts.model_dump(), "consensus": consensus(pcts),
                   "divergence": divergence_index(pcts)},
        "signal": sig.model_dump(),
        "witness": price_witness(ds, cid, client).model_dump(),
        "compliance": compliance_gap(ds, cid, config.END_YEAR).model_dump(),
        "forecast": fc.model_dump(),
        "claims": claim_table(ds, cid, config.END_YEAR, client),
        "peers": sorted(peers, key=lambda p: -(p["evidence_total"] or 0)),
    }


def build(offline: bool = True, retrain: bool = False) -> dict:
    client = get_default_client(offline=offline)
    ds = ingest.load()
    model = _load_or_train(ds, client, retrain=retrain)
    sigs = compute_all(ds, client)
    pcts = normalize_raters(ds, config.END_YEAR)

    companies, matrix = [], []
    for cid in ds.demo_ids():
        comp = ds.company(cid)
        sig = sigs[cid]
        es = evidence_score(ds, cid, config.END_YEAR, client)
        cg = compliance_gap(ds, cid, config.END_YEAR)
        fc = forecast(ds, cid, model, client)
        row = {
            "id": cid, "name": comp.name, "ticker": comp.ticker, "sector": comp.sector,
            "country": comp.country, "evidence_total": es.total, "confidence": es.confidence,
            "consensus": consensus(pcts[cid]), "divergence": divergence_index(pcts[cid]),
            "evidence_gap": sig.evidence_gap, "momentum": sig.momentum, "quadrant": sig.quadrant,
            "is_underpriced_improver": sig.is_underpriced_improver,
            "compliance_score": cg.score, "forecast": fc.predicted_score,
        }
        companies.append(row)
        matrix.append({"id": cid, "name": comp.name, "x": sig.esg_today, "y": sig.momentum,
                       "quadrant": sig.quadrant, "size": es.total,
                       "is_underpriced_improver": sig.is_underpriced_improver})
        _dump(config.OUT_DIR / "company" / f"{cid}.json", _company_detail(ds, cid, sig, model, client))

    improvers = [r for r in companies if r["is_underpriced_improver"]]
    _dump(config.OUT_DIR / "companies.json", companies)
    _dump(config.OUT_DIR / "matrix.json", matrix)
    _dump(config.OUT_DIR / "signals.json", improvers)
    return {"companies": len(companies), "improvers": len(improvers),
            "model_val_error": model.val_error}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="zero network: SQLite + cache + saved model")
    ap.add_argument("--retrain", action="store_true", help="retrain and overwrite the saved forecaster")
    args = ap.parse_args()
    summary = build(offline=args.offline, retrain=args.retrain)
    print(f"Pipeline done: {summary}")
    print(f"  -> {config.OUT_DIR}")


if __name__ == "__main__":
    main()
