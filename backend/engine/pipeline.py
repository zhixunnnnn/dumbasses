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
from .rating_score import rating_from_pcts, rating_score, rating_series
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


def _impact_block(cid: str) -> Optional[dict]:
    """Impact materiality (Climate TRACE owned-asset CO2e) for one company, with its rank and
    share across the covered panel. None when no clean owner match exists (renders N.A.)."""
    try:
        from backend.data.climate_trace import cached, cached_impact_for
    except Exception:
        return None
    rec = cached_impact_for(cid)
    if not rec:
        return None
    # drop any partially-elapsed current year from the trajectory (not comparable to full years)
    rec = {**rec, "annual": [a for a in (rec.get("annual") or []) if a["year"] < config.CURRENT_YEAR]}
    companies = (cached().get("companies") or {})
    totals = {c: r.get("total_emissions_tonnes") for c, r in companies.items()
              if r.get("total_emissions_tonnes")}
    panel_total = sum(totals.values()) or None
    ranked = sorted(totals, key=lambda c: -totals[c])
    mine = rec.get("total_emissions_tonnes")
    return {
        **rec,
        "company_id": cid,
        "rank": (ranked.index(cid) + 1) if cid in ranked else None,
        "peers": len(totals),
        "panel_share": round(mine / panel_total, 3) if (mine and panel_total) else None,
    }


def _panel_intensities() -> dict[str, Optional[float]]:
    """Carbon intensity (tCO2e per $M revenue) for every company that has both emissions
    (Climate TRACE) and revenue (Yahoo) — the input to the peer-ranked impact score."""
    from .double_materiality import carbon_intensity
    try:
        from backend.data.climate_trace import cached as ct_cached
        from backend.data.fundamentals import cached as fund_cached
    except Exception:
        return {}
    emis = {c: r.get("total_emissions_tonnes")
            for c, r in (ct_cached().get("companies") or {}).items()}
    funds = fund_cached().get("companies") or {}
    out: dict[str, Optional[float]] = {}
    for c in set(emis) | set(funds):
        fin = (funds.get(c) or {}).get("financials") or {}
        out[c] = carbon_intensity(emis.get(c), fin.get("market_cap"), fin.get("currency"))
    return out


def _emission_momentum(cid: str) -> Optional[float]:
    """Redefined ESG momentum: the annualised % change in owned-asset emissions (Climate
    TRACE), sign-flipped so FALLING emissions read as POSITIVE (a company decarbonising is
    improving). Real trajectory; None below two full years of coverage."""
    try:
        from backend.data.climate_trace import cached_impact_for
        rec = cached_impact_for(cid)
    except Exception:
        return None
    annual = [a for a in ((rec or {}).get("annual") or []) if a["year"] < config.CURRENT_YEAR]
    if len(annual) < 2:
        return None
    xs = [a["year"] for a in annual]
    ys = [a["emissions"] for a in annual]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0 or my <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom   # tonnes / yr
    return round(-(slope / my) * 100, 1)   # falling emissions -> positive momentum


def _emission_quadrant(rating: Optional[float], emom: Optional[float]) -> Optional[str]:
    """Quadrant on ESG rating (x) x emission momentum (y). Keys are kept but their meaning is
    now: FUTURE_LEADERS = rated well AND decarbonising; HIDDEN_WINNERS = rated low but
    decarbonising (turnaround); OVERRATED = rated well but emissions rising (transition risk);
    VALUE_TRAPS = rated low and emissions rising (laggard)."""
    if rating is None or emom is None:
        return None
    x_high = rating >= config.QUADRANT_RATING_SPLIT
    y_up = emom > 0   # emissions falling = improving
    return (("FUTURE_LEADERS" if x_high else "HIDDEN_WINNERS") if y_up
            else ("OVERRATED" if x_high else "VALUE_TRAPS"))


def _sg_signal(ds, cid: str, client) -> tuple:
    """Real Social & Governance pillar signals from the company's OWN report disclosures
    (the SASB material topics workforce-safety for S, grid-resiliency for G), via the same
    LLM claim extraction the app already scrapes. Returns
    (s_signal, s_sources, g_signal, g_sources) — a pillar is real only when the company
    actually disclosed that topic; otherwise None, so the pillar falls back to the agency
    reference. No seeded evidence is ever used (guardrail: real claims only)."""
    try:
        from backend.data.realclaims import cached_claims_for
        real = cached_claims_for(cid, year=config.END_YEAR)
    except Exception:
        real = None
    rows = (real or {}).get("claims") or []
    if not rows:
        return (None, None, None, None)          # no real extraction -> agency reference
    pillars_disclosed = {c.get("pillar") for c in rows}
    es = evidence_score(ds, cid, config.END_YEAR, client)   # computed from the REAL claims
    p = es.pillars
    s = p.get("S") if ("S" in pillars_disclosed and p.get("S") is not None) else None
    g = p.get("G") if ("G" in pillars_disclosed and p.get("G") is not None) else None
    return (s, ["company report · workforce safety"] if s is not None else None,
            g, ["company report · grid resiliency"] if g is not None else None)


def _environmental_signals(ds) -> dict[str, tuple]:
    """{cid: (env_score, sources)} — the OBJECTIVE Environmental-pillar signal (CDP grade +
    Climate TRACE carbon intensity) that overrides the agency headline for E, so the rating
    reflects measured climate performance instead of agency opinion."""
    from . import double_materiality as dm
    from .rating_score import environmental_signal

    cleaned, _flagged = dm.guard_intensities(_panel_intensities())
    impact = dm.impact_scores(cleaned)
    return {cid: environmental_signal(ds, cid, impact.get(cid)) for cid in ds.demo_ids()}


def _double_materiality_block(cid: str, financial: Optional[float],
                              financial_prov, intensities: dict) -> dict:
    """The ESRS composite for one company (financial x impact - greenwashing)."""
    from . import double_materiality as dm

    cleaned, flagged = dm.guard_intensities(intensities)
    scores = dm.impact_scores(cleaned)
    impact = scores.get(cid)
    my_int = cleaned.get(cid)
    ranked = sorted([c for c, v in cleaned.items() if v is not None], key=lambda c: cleaned[c])
    # web-scraped greenwashing reality-check: controversy/accusation headlines from the open web.
    gw = {}
    try:
        from backend.data.greenwashing import cached_greenwashing_for
        gw = cached_greenwashing_for(cid)
    except Exception:
        gw = {}
    penalty, drivers = dm.greenwashing_penalty(financial, impact,
                                               controversies=gw.get("controversy_count", 0))
    comp, note = dm.composite(financial, impact, penalty)
    if cid in flagged:
        note = ("Climate TRACE appears to under-attribute this owner's emissions (too few "
                "assets for its size), so the impact half is excluded and the composite is the "
                "financial half only.")
    return {
        "company_id": cid, "financial": financial, "impact": impact, "composite": comp,
        "weight_financial": config.DM_WEIGHT_FINANCIAL, "weight_impact": config.DM_WEIGHT_IMPACT,
        "carbon_intensity": my_int,
        "intensity_rank": (ranked.index(cid) + 1) if cid in ranked else None,
        "intensity_peers": len(ranked),
        "greenwashing_penalty": penalty, "greenwashing_drivers": drivers,
        "greenwashing_headlines": gw.get("headlines", []),
        "under_attributed": cid in flagged,
        "provenance": financial_prov, "note": note,
    }


def _real_only(value, provenance):
    """Show a rater-derived figure only when it is fully REAL. A "mixed" or "illustrative"
    consensus/divergence is N.A. for a CGS investor — no seeded numbers on the terminal."""
    return value if provenance == "real" else None


def _fundamentals_block(cid: str) -> Optional[dict]:
    """Real Yahoo valuation/financials/analyst data for the CGS finance panel. None when
    Yahoo returned nothing for this ticker (renders N.A.)."""
    try:
        from backend.data.fundamentals import fundamentals_for
    except Exception:
        return None
    return fundamentals_for(cid)


def _company_detail(ds, cid, sig, model, client, bench_rows) -> dict:
    comp = ds.company(cid)
    all_pcts = normalize_raters(ds, config.END_YEAR)
    pcts = all_pcts[cid]
    envs = _environmental_signals(ds)
    env = envs.get(cid, (None, None))
    es = evidence_score(ds, cid, config.END_YEAR, client)
    # the ESG RATING is the headline score. Agencies inform Social & Governance (reference
    # only — differing black-box methods); the Environmental pillar is driven by the OBJECTIVE
    # signal (CDP + Climate TRACE) so it reflects measured climate performance.
    sg = _sg_signal(ds, cid, client)
    rating = rating_from_pcts(ds, cid, config.END_YEAR, pcts, env_signal=env[0], env_sources=env[1],
                              s_signal=sg[0], s_sources=sg[1], g_signal=sg[2], g_sources=sg[3])
    rating_hist = [{"year": r.year, "total": r.total, "pillars": r.pillars,
                    "provenance": r.provenance} for r in rating_series(ds, cid)]
    # the latest trajectory point is the headline (E-enhanced), so they never disagree.
    for pt in rating_hist:
        if pt["year"] == config.END_YEAR:
            pt["total"], pt["pillars"] = rating.total, rating.pillars
    series = [{"year": e.year, "total": e.total, "pillars": e.pillars, "confidence": e.confidence}
              for e in evidence_series(ds, cid, client)]
    fc = forecast(ds, cid, model, client)
    peers = [{"id": c.company_id, "name": c.name,
              "evidence_total": (evidence_score(ds, c.company_id, config.END_YEAR, client).total),
              "rating_total": (lambda psg: rating_from_pcts(
                  ds, c.company_id, config.END_YEAR, all_pcts[c.company_id],
                  env_signal=envs.get(c.company_id, (None, None))[0],
                  env_sources=envs.get(c.company_id, (None, None))[1],
                  s_signal=psg[0], s_sources=psg[1], g_signal=psg[2], g_sources=psg[3]).total
              )(_sg_signal(ds, c.company_id, client))}
             for c in ds.companies.values()
             if c.scope == "demo" and c.sector == comp.sector and c.company_id != cid]
    # Claims/evidence are REAL-only: show only LLM-extracted claims from the company's own
    # report (realclaims cache). No seeded/illustrative claims — an empty table when we have
    # no real extraction, never a fabricated one.
    claims = {"claims": [], "absent": [], "live": False}
    try:
        from backend.data.realclaims import cached_claims_for

        real_claims = cached_claims_for(cid, year=config.END_YEAR)
        if real_claims and real_claims.get("claims"):
            claims = real_claims
    except Exception:
        pass
    return {
        "company": comp.model_dump(),
        "rating": rating.model_dump(),
        "rating_series": rating_hist,
        "impact": _impact_block(cid),
        "double_materiality": _double_materiality_block(
            cid, rating.total, rating.provenance, _panel_intensities()),
        "fundamentals": _fundamentals_block(cid),
        "evidence": es.model_dump(),
        "series": series,
        "raters": {**pcts.model_dump(),
                   # real-only: a mixed/illustrative consensus or divergence is N.A.
                   "consensus": _real_only(consensus(pcts), pcts.provenance()),
                   "divergence": _real_only(divergence_index(pcts), pcts.provenance()),
                   "consensus_provenance": pcts.provenance(),
                   "divergence_provenance": pcts.provenance(),
                   "contributing": pcts.contributing(),
                   **_rater_provenance(cid, pcts)},
        "signal": sig.model_dump(),
        "witness": price_witness(ds, cid, client).model_dump(),
        "compliance": compliance_gap(ds, cid, config.END_YEAR).model_dump(),
        "forecast": fc.model_dump(),
        "claims": claims,
        "peers": sorted(peers, key=lambda p: -(p["rating_total"] or 0)),
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
    envs = _environmental_signals(ds)  # objective E signal per company, for the headline rating

    sectors_map = {r["reg_id"]: r.get("applies_to_sectors", [])
                   for r in config.load_json("regulations.json")["regulations"]}
    reg_tally = {r.reg_id: {"MET": 0, "PARTIAL": 0, "MISSING": 0, "NA": 0} for r in ds.regulations}

    companies, matrix = [], []
    for cid in ds.demo_ids():
        comp = ds.company(cid)
        sig = sigs[cid]
        es = evidence_score(ds, cid, config.END_YEAR, client)
        _sg = _sg_signal(ds, cid, client)
        rt = rating_from_pcts(ds, cid, config.END_YEAR, pcts[cid],
                              env_signal=envs.get(cid, (None, None))[0],
                              env_sources=envs.get(cid, (None, None))[1],
                              s_signal=_sg[0], s_sources=_sg[1],
                              g_signal=_sg[2], g_sources=_sg[3])
        cg = compliance_gap(ds, cid, config.END_YEAR)
        # finance columns (smartass-style): last price, weekly change, and a recent
        # close-price spark for the screener trend cell.
        closes = [c.close for c in ds.prices.get(cid, [])]
        last_px = closes[-1] if closes else None
        # week-over-week change, skipping a stale duplicate final bar: the latest weekly
        # snapshot often just repeats last week's close, which would zero out the change —
        # so compare against the most recent DIFFERENT prior close (the last real move).
        cl = list(closes)
        while len(cl) >= 2 and cl[-1] == cl[-2]:
            cl.pop()
        prev_px = cl[-2] if len(cl) >= 2 else None
        chg_pct = round((last_px - prev_px) / prev_px * 100, 2) if (last_px and prev_px) else None
        spark = [round(c, 4) for c in closes[-24:]]
        # REDEFINED ESG momentum = emission trajectory; quadrant = rating x emission momentum.
        emom = _emission_momentum(cid)
        quad = _emission_quadrant(rt.total, emom)
        sig.quadrant = quad
        sig.quadrant_provenance = rt.provenance   # quadrant now = real rating x real emissions
        sig.momentum = emom
        sig.is_underpriced_improver = bool(emom is not None and emom >= config.IMPROVER_MIN_EMOM
                                           and sig.price_flat)
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
            "country": comp.country,
            "rating_total": rt.total, "rating_provenance": rt.provenance,
            "rating_coverage": rt.coverage,
            "price": last_px, "price_chg": chg_pct, "spark": spark,
            "evidence_total": es.total, "confidence": es.confidence,
            "consensus": _real_only(consensus(pcts[cid]), pcts[cid].provenance()),
            "divergence": _real_only(divergence_index(pcts[cid]), pcts[cid].provenance()),
            "rater_provenance": pcts[cid].provenance(),
            "evidence_pct": sig.evidence_pct, "evidence_basis": sig.evidence_basis,
            "evidence_peers": sig.evidence_peers,
            "evidence_gap": sig.evidence_gap, "momentum": sig.momentum, "quadrant": sig.quadrant,
            "emission_momentum": emom,
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
        # matrix: x = ESG rating (the score), y = emission momentum (decarbonising = up)
        matrix.append({"id": cid, "name": comp.name, "x": rt.total, "y": emom,
                       "quadrant": sig.quadrant, "size": rt.total,
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
