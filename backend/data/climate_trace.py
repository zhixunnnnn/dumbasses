"""Impact materiality from Climate TRACE — each utility's REAL owned-asset CO2e.

This is the outward half of *double materiality*. The ESG rating captures financial
materiality (how ESG risk prices back into the company); Climate TRACE captures IMPACT
materiality (how much the company's physical power assets actually emit into the world).
Power generators are exactly what Climate TRACE inventories, so the figures are real,
per-asset and named — not a model estimate of a company total.

We resolve each company to a Climate TRACE OWNER id once (config/climate_trace_owners.json,
hand-verified) and pull that owner's 2023 emissions: the group total, the monthly path, the
subsector mix, and the top emitting assets by name. A company with no clean owner match is
absent from the map and renders N.A. — never a fabricated number (guardrail T7).

The Climate TRACE toolkit is loaded the same way the smartass app loads it: its REST client
(api/client.py) is imported BY FILE PATH, because importing the `climate_trace_tools`
package top-level pulls in a BigQuery client that needs GCP credentials we do not have. The
v7 REST API itself needs no auth.

    python -m backend.data.climate_trace           # (re)build the cache from the live API
    python -m backend.data.climate_trace --show    # print the cache, fetch nothing
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Optional

from backend.engine import config

CACHE_FILE = config.CACHE_DIR / "climate_trace.json"
YEAR = config.END_YEAR
GAS = "co2e_100yr"
SOURCE_URL = "https://api.climatetrace.org/v7"


def _owner_map() -> dict:
    return config.load_json("climate_trace_owners.json")


def _load_ct_client():
    """Import climate_trace_tools/api/client.py directly, bypassing the package __init__
    (whose top-level BigQuery import needs GCP creds). The REST client needs no auth."""
    base = Path(importlib.util.find_spec("climate_trace_tools").origin).parent
    client_path = base / "api" / "client.py"
    spec = importlib.util.spec_from_file_location("_ct_api", client_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _shape(owner_id: str, owner_name: str, note: Optional[str], agg: dict, sources: list) -> dict:
    """Compact one owner's API payloads into the record the UI renders."""
    totals = (agg.get("totals") or {}).get("summaries") or []
    total = totals[0].get("emissionsQuantity") if totals else None

    monthly = []
    for pt in ((agg.get("totals") or {}).get("timeseries") or []):
        if pt.get("year") == YEAR and pt.get("emissionsQuantity") is not None:
            monthly.append({"month": pt.get("month"), "emissions": pt.get("emissionsQuantity")})
    monthly.sort(key=lambda m: m.get("month") or 0)

    assets = []
    for s in sources if isinstance(sources, list) else []:
        q = s.get("emissionsQuantity")
        if not q:
            continue
        assets.append({
            "name": s.get("name"),
            "sector": s.get("sector"),
            "subsector": s.get("subsector"),
            "country": s.get("country"),
            "emissions": q,
        })
    assets.sort(key=lambda a: a["emissions"], reverse=True)

    # subsector mix over the located assets (electricity-generation vs the rest).
    mix: dict[str, float] = {}
    for a in assets:
        key = a.get("subsector") or a.get("sector") or "other"
        mix[key] = mix.get(key, 0.0) + a["emissions"]
    subsector_mix = sorted(({"subsector": k, "emissions": v} for k, v in mix.items()),
                           key=lambda x: x["emissions"], reverse=True)

    return {
        "owner_id": owner_id,
        "owner_name": owner_name,
        "note": note,
        "year": YEAR,
        "gas": GAS,
        "total_emissions_tonnes": total,
        "asset_count": len(assets),
        "top_assets": assets[:8],
        "subsector_mix": subsector_mix,
        "monthly": monthly,
        "provenance": "real",
        "source": "Climate TRACE v7",
        "source_url": SOURCE_URL,
    }


def _annual_series(api, owner_id: str) -> list[dict]:
    """Real annual total CO2e for one owner, newest coverage kept. A year Climate TRACE does
    not cover for this owner comes back as 0 — that is missing coverage, not a real zero, so
    it is dropped (never plotted as if the company emitted nothing)."""
    out = []
    # stop before the CURRENT year — it is only partially elapsed, so its total is not
    # comparable to full years and would read as a false cliff on the trajectory.
    for year in range(2019, config.CURRENT_YEAR):
        try:
            agg = api.get_aggregate_emissions(owner_ids=owner_id, year=year, gas=GAS)
        except Exception:
            continue
        summ = (agg.get("totals") or {}).get("summaries") or []
        val = summ[0].get("emissionsQuantity") if summ else None
        if val:
            out.append({"year": year, "emissions": val})
    return out


def refresh() -> dict:
    """Fetch every mapped owner's emissions and rewrite the cache. A failed fetch keeps the
    existing cache rather than blanking it."""
    owners = (_owner_map().get("owners") or {})
    try:
        api = _load_ct_client()
    except Exception as exc:
        print(f"Climate TRACE toolkit not importable ({exc}) — keeping existing cache.")
        return cached().get("companies") or {}

    companies: dict[str, dict] = {}
    for cid, info in owners.items():
        oid = info["owner_id"]
        try:
            agg = api.get_aggregate_emissions(owner_ids=oid, year=YEAR, gas=GAS)
            sources = api.get_sources(owner_ids=oid, year=YEAR, gas=GAS, limit=200)
            annual = _annual_series(api, oid)
        except Exception as exc:
            print(f"  {cid}: fetch failed ({type(exc).__name__}: {exc}) — skipping this owner.")
            continue
        rec = _shape(oid, info.get("owner_name", ""), info.get("note"), agg, sources)
        rec["annual"] = annual
        companies[cid] = rec
        print(f"  {cid}: {rec['owner_name']} — {rec['total_emissions_tonnes']} tCO2e "
              f"across {rec['asset_count']} assets")

    if not companies:
        print("Climate TRACE returned nothing for any owner — keeping existing cache.")
        return cached().get("companies") or {}

    CACHE_FILE.write_text(json.dumps({
        "year": YEAR, "gas": GAS, "resolved_on": _owner_map().get("resolved_on"),
        "source": SOURCE_URL, "companies": companies,
    }, indent=1), "utf-8")
    print(f"Wrote {len(companies)} owners to {CACHE_FILE}")
    return companies


def cached() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def cached_impact_for(cid: str) -> Optional[dict]:
    """The cached impact record for one company, or None when we have no clean owner match
    or no cache. None means N.A. in the UI — never a fabricated zero."""
    return (cached().get("companies") or {}).get(cid)


if __name__ == "__main__":
    import sys

    if "--show" in sys.argv:
        print(json.dumps(cached(), indent=1)[:4000])
    else:
        refresh()
