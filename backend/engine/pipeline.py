"""Orchestrate the engine and precompute the dashboard JSON.

    python -m backend.engine.pipeline            # live LLM if OPENROUTER_API_KEY set
    python -m backend.engine.pipeline --offline  # demo mode: SQLite + cache + saved model, zero network

Writes backend/out/{companies,matrix,signals}.json and out/company/{id}.json.
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

import joblib

from . import config, ingest
from .benchmarks import get_benchmarks
from .divergence import divergence_index
from .llm import get_default_client
from .normalize import consensus, normalize_raters
from .predict import data_fingerprint, forecast, train
from .regulations import compliance_gap
from .score import claim_table, evidence_score, evidence_series
from .signal import compute_all
from .witness import price_witness

MODEL_PATH = config.MODELS_DIR / "forecaster.joblib"


def _load_or_train(ds, client, retrain=False):
    """Reuse the saved forecaster only while it still describes THIS data. The stamp
    carries END_YEAR plus a fingerprint of the real rating panel, so moving the window or
    re-extracting the ratings retrains instead of silently serving yesterday's fit."""
    if MODEL_PATH.exists() and not retrain:
        try:
            saved = joblib.load(MODEL_PATH)
            if getattr(saved, "stamp", None) == data_fingerprint():
                return saved
        except Exception:
            pass                                   # unreadable or older layout -> retrain
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


def _rater_provenance(cid: str, pcts) -> dict:
    """Per-channel provenance so the UI can label every rater honestly. Precedence matches
    the ingest overlay: a hand-entered reading outranks a rating the company disclosed in
    its own report, which outranks the (now stale) KnowESG scrape, which outranks the seed.
    `real_raters` comes straight off the percentiles — one source of truth for realness."""
    try:
        from backend.data.realraters import cached_real_raters

        scraped = cached_real_raters().get(cid) or {}
    except Exception:
        scraped = {}
    try:
        from .manual_raters import by_company

        manual = by_company().get(cid) or {}
    except Exception:
        manual = {}
    try:
        from backend.data.realratings import scored_by_year

        disclosed = scored_by_year().get(cid, {}).get(config.END_YEAR) or {}
    except Exception:
        disclosed = {}
    try:
        from backend.data.realcdp import cached_cdp, disclosure_status

        cdp_table = (cached_cdp().get("companies") or {}).get(cid) or {}
        declined = cid in disclosure_status()
    except Exception:
        cdp_table, declined = {}, False

    provenance = {}
    for rater in ("msci", "sp", "sustainalytics", "cdp"):
        entry = manual.get(rater)
        if entry:
            provenance[rater] = {"real": True, "source": "hand-entered",
                                 "url": entry["source_url"], "observed_on": entry["observed_on"],
                                 "value_raw": entry["value_raw"]}
        elif disclosed.get(rater):
            row = disclosed[rater]
            provenance[rater] = {"real": True, "source": row.get("source_title") or "company report",
                                 "url": row.get("source_url"),
                                 "observed_on": str(row.get("assessment_year") or ""),
                                 "value_raw": row.get("value_raw")}
        elif rater == "msci" and scraped.get("msci"):
            # KnowESG dropped its numeric scores, so this is shown but not counted as
            # real (config.TRUST_SCRAPED_RATERS_AS_REAL).
            provenance[rater] = {"real": config.TRUST_SCRAPED_RATERS_AS_REAL,
                                 "source": f"{scraped.get('source')} (stale)",
                                 "url": scraped.get("url"), "observed_on": None,
                                 "value_raw": scraped.get("msci")}
        elif rater == "cdp" and cdp_table.get("cdp"):
            provenance[rater] = {"real": True, "source": cdp_table.get("source"),
                                 "url": cdp_table.get("url"),
                                 "observed_on": str(cdp_table.get("assessment_year") or ""),
                                 "value_raw": cdp_table["cdp"]}
        elif rater == "cdp" and declined:
            # NOT a bad score: the company chose not to respond to CDP. Surfaced as a
            # disclosure fact so the UI can say so instead of showing an empty channel.
            provenance[rater] = {"real": False, "source": cdp_table.get("source"),
                                 "url": cdp_table.get("url"),
                                 "observed_on": str(cdp_table.get("assessment_year") or ""),
                                 "value_raw": None, "status": cdp_table.get("status")}
        else:
            provenance[rater] = {"real": False, "source": None, "url": None,
                                 "observed_on": None, "value_raw": None}
    msci = provenance["msci"]
    return {
        "real_raters": list(pcts.real_raters),
        "rater_provenance": provenance,
        # kept for the existing MSCI-specific UI copy
        "msci_real": msci["real"], "msci_source": msci["source"], "msci_url": msci["url"],
    }


def _latest_real_raters(cid: str) -> list[dict]:
    """The most recent REAL rating on each channel, WITH ITS OWN OBSERVATION YEAR.

    Real ratings are attached to the year they were actually measured in, which is not
    always the analysis year — CDP's current scores are 2025 observations while END_YEAR
    is 2024. Re-dating them to END_YEAR would falsify the observation, and dropping them
    would hide real data we hold, so they travel separately with their year attached and
    never feed the END_YEAR consensus/divergence.
    """
    out: dict[str, dict] = {}
    for module_name, source in (("backend.data.realratings", "company report"),
                                ("backend.data.realcdp", "CDP scores table")):
        try:
            module = __import__(module_name, fromlist=["scored_by_year"])
            years = module.scored_by_year().get(cid) or {}
        except Exception:
            continue
        for year, entries in years.items():
            for rater, entry in entries.items():
                value = entry.get("value_raw") if isinstance(entry, dict) else entry
                if not value:
                    continue
                prior = out.get(rater)
                if prior and prior["year"] >= year:
                    continue
                url = entry.get("source_url") if isinstance(entry, dict) else None
                out[rater] = {"rater": rater, "value": value, "year": year,
                              "source": source, "url": url, "provenance": "real"}
    return [out[k] for k in sorted(out)]


def _cdp_disclosure(cid: str) -> Optional[dict]:
    """CDP listed the company but it did not respond. A fact, never a score."""
    try:
        from backend.data.realcdp import disclosure_status

        info = disclosure_status().get(cid)
    except Exception:
        return None
    if not info:
        return None
    return {"rater": "cdp", "status": info.get("status"), "year": info.get("assessment_year"),
            "source": info.get("source"), "url": info.get("url")}


def _benchmark_block(bench_rows, industry) -> dict:
    """The industry benchmark a company is read against — a stored override (CGSI) when
    one exists, otherwise the panel median. Passed in already computed: the median is a
    panel-wide scoring pass, far too expensive to redo per company."""
    by_metric = {r["metric"]: r for r in bench_rows if r["industry"] == industry}
    total = by_metric.get("total")
    return {
        "industry": industry,
        "peers": total.get("peers") if total else None,
        "total": total["value"] if total else config.NA,
        "pillars": {p: (by_metric[p]["value"] if p in by_metric else config.NA)
                    for p in ("E", "S", "G")},
        "source": total["source"] if total else None,
        "is_override": bool(total and total["is_override"]),
    }


def _company_detail(ds, cid, sig, model, client, bench_rows) -> dict:
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

        claims = cached_claims_for(cid, absent=claims.get("absent", []),
                                   year=config.END_YEAR) or claims
    except Exception:
        pass
    return {
        "company": comp.model_dump(),
        "evidence": es.model_dump(),
        "series": series,
        "raters": {**pcts.model_dump(), "consensus": consensus(pcts),
                   "divergence": divergence_index(pcts),
                   # "real" | "mixed" | "illustrative" for BOTH figures: they run over the
                   # same contributing set, so one label describes both.
                   "consensus_provenance": pcts.provenance(),
                   "divergence_provenance": pcts.provenance(),
                   "contributing": pcts.contributing(),
                   **_rater_provenance(cid, pcts)},
        "signal": sig.model_dump(),
        "witness": price_witness(ds, cid, client).model_dump(),
        "compliance": compliance_gap(ds, cid, config.END_YEAR).model_dump(),
        "forecast": fc.model_dump(),
        "claims": claims,
        "peers": sorted(peers, key=lambda p: -(p["evidence_total"] or 0)),
        # real observations that sit OUTSIDE the analysis year, shown with their own year
        "latest_real_raters": _latest_real_raters(cid),
        "cdp_disclosure": _cdp_disclosure(cid),
        "benchmark": _benchmark_block(bench_rows, comp.sasb_industry),
    }


def build(offline: bool = True, retrain: bool = False) -> dict:
    client = get_default_client(offline=offline)
    ds = ingest.load()
    model = _load_or_train(ds, client, retrain=retrain)
    sigs = compute_all(ds, client)
    pcts = normalize_raters(ds, config.END_YEAR)
    bench_rows = get_benchmarks(ds)   # one panel-wide pass, reused by every company row

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
        bench = _benchmark_block(bench_rows, comp.sasb_industry)
        row = {
            "id": cid, "name": comp.name, "ticker": comp.ticker, "sector": comp.sector,
            "country": comp.country, "evidence_total": es.total, "confidence": es.confidence,
            "consensus": consensus(pcts[cid]), "divergence": divergence_index(pcts[cid]),
            "rater_provenance": pcts[cid].provenance(),
            "evidence_pct": sig.evidence_pct, "evidence_basis": sig.evidence_basis,
            "evidence_peers": sig.evidence_peers,
            "evidence_gap": sig.evidence_gap, "momentum": sig.momentum, "quadrant": sig.quadrant,
            "is_underpriced_improver": sig.is_underpriced_improver,
            "compliance_score": cg.score, "compliance_provenance": cg.provenance,
            "forecast": fc.predicted_score,
            "forecast_label": fc.predicted_label, "forecast_direction": fc.direction,
            "forecast_baseline_only": fc.baseline_only,
            # same real/mixed/illustrative convention as rater_provenance, but for the
            # company's own rating HISTORY — which is what the prediction rests on
            "forecast_provenance": fc.provenance,
            "forecast_accuracy_note": fc.accuracy_note,
            "benchmark_total": bench["total"], "benchmark_source": bench["source"],
            "benchmark_peers": bench["peers"],
            "regulations": reg_cells,
        }
        companies.append(row)
        matrix.append({"id": cid, "name": comp.name, "x": sig.esg_today, "y": sig.momentum,
                       "quadrant": sig.quadrant, "size": es.total,
                       "is_underpriced_improver": sig.is_underpriced_improver})
        _dump(config.OUT_DIR / "company" / f"{cid}.json", _company_detail(ds, cid, sig, model, client, bench_rows))

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
