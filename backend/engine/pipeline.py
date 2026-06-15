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


def _applies_to_text(reg, sectors_map) -> str:
    """Human-readable 'who this regulation binds', for the catalog/filter tooltip."""
    sectors = sectors_map.get(reg.reg_id) or []
    if sectors:
        return ", ".join(sectors)
    if reg.scope == "MAS-FI":
        return "Financial institutions"
    if reg.scope.startswith("SGX"):
        return "All SGX-listed"
    if reg.scope.startswith("ASEAN"):
        return "ASEAN-listed"
    return "All"


def _rater_provenance(cid: str) -> dict:
    """Mark MSCI as real (scraped) where we have it; S&P + Sustainalytics are always
    seeded/illustrative. Lets the UI label provenance honestly."""
    try:
        from backend.data.realraters import cached_real_raters

        info = cached_real_raters().get(cid)
    except Exception:
        info = None
    return {
        "msci_real": bool(info),
        "msci_source": info.get("source") if info else None,
        "msci_url": info.get("url") if info else None,
    }


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
    claims = claim_table(ds, cid, config.END_YEAR, client)
    try:
        from backend.data.realclaims import cached_claims_for

        claims = cached_claims_for(cid, absent=claims.get("absent", [])) or claims
    except Exception:
        pass
    return {
        "company": comp.model_dump(),
        "evidence": es.model_dump(),
        "series": series,
        "raters": {**pcts.model_dump(), "consensus": consensus(pcts),
                   "divergence": divergence_index(pcts), **_rater_provenance(cid)},
        "signal": sig.model_dump(),
        "witness": price_witness(ds, cid, client).model_dump(),
        "compliance": compliance_gap(ds, cid, config.END_YEAR).model_dump(),
        "forecast": fc.model_dump(),
        "claims": claims,
        "peers": sorted(peers, key=lambda p: -(p["evidence_total"] or 0)),
    }


def build(offline: bool = True, retrain: bool = False) -> dict:
    client = get_default_client(offline=offline)
    ds = ingest.load()
    model = _load_or_train(ds, client, retrain=retrain)
    sigs = compute_all(ds, client)
    pcts = normalize_raters(ds, config.END_YEAR)

    sectors_map = {r["reg_id"]: r.get("applies_to_sectors", [])
                   for r in config.load_json("regulations.json")["regulations"]}
    reg_tally = {r.reg_id: {"MET": 0, "PARTIAL": 0, "MISSING": 0, "NA": 0} for r in ds.regulations}

    companies, matrix = [], []
    for cid in ds.demo_ids():
        comp = ds.company(cid)
        sig = sigs[cid]
        es = evidence_score(ds, cid, config.END_YEAR, client)
        cg = compliance_gap(ds, cid, config.END_YEAR)
        fc = forecast(ds, cid, model, client)
        # flatten the applicable regs (+ status) onto the row so the Screener can filter
        # by regulation without an extra round-trip. not_in_force -> status "NA".
        reg_cells = []
        for rs in (cg.met + cg.partial + cg.missing + cg.not_in_force):
            reg_cells.append({"reg_id": rs.reg_id, "name": rs.name, "status": rs.status})
            reg_tally[rs.reg_id][rs.status] += 1
        row = {
            "id": cid, "name": comp.name, "ticker": comp.ticker, "sector": comp.sector,
            "country": comp.country, "evidence_total": es.total, "confidence": es.confidence,
            "consensus": consensus(pcts[cid]), "divergence": divergence_index(pcts[cid]),
            "evidence_gap": sig.evidence_gap, "momentum": sig.momentum, "quadrant": sig.quadrant,
            "is_underpriced_improver": sig.is_underpriced_improver,
            "compliance_score": cg.score, "forecast": fc.predicted_score,
            "regulations": reg_cells,
        }
        companies.append(row)
        matrix.append({"id": cid, "name": comp.name, "x": sig.esg_today, "y": sig.momentum,
                       "quadrant": sig.quadrant, "size": es.total,
                       "is_underpriced_improver": sig.is_underpriced_improver})
        _dump(config.OUT_DIR / "company" / f"{cid}.json", _company_detail(ds, cid, sig, model, client))

    # regulation registry/catalog: metadata + how many demo names each regime binds and their status
    reg_catalog = []
    for r in ds.regulations:
        t = reg_tally[r.reg_id]
        src = ds.reg_source.get(r.reg_id)
        n_scraped = sum(1 for (_cid, rid), ev in ds.reg_evidence.items()
                        if rid == r.reg_id and ev.status in ("MET", "PARTIAL", "MISSING"))
        reg_catalog.append({
            "reg_id": r.reg_id, "name": r.name, "jurisdiction": r.jurisdiction,
            "scope": r.scope, "requirement": r.requirement, "effective_year": r.effective_year,
            "applies_to": _applies_to_text(r, sectors_map),
            "n_applicable": t["MET"] + t["PARTIAL"] + t["MISSING"] + t["NA"],
            "n_met": t["MET"], "n_partial": t["PARTIAL"], "n_missing": t["MISSING"], "n_na": t["NA"],
            "n_scraped": n_scraped,
            "source_url": src.source_url if src else None,
            "source_excerpt": src.source_excerpt if src else None,
        })

    improvers = [r for r in companies if r["is_underpriced_improver"]]
    _dump(config.OUT_DIR / "companies.json", companies)
    _dump(config.OUT_DIR / "matrix.json", matrix)
    _dump(config.OUT_DIR / "signals.json", improvers)
    _dump(config.OUT_DIR / "regulations.json", reg_catalog)
    return {"companies": len(companies), "improvers": len(improvers),
            "regulations": len(reg_catalog), "model_val_error": model.val_error}


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
