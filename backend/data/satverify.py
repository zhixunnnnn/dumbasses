"""Upgrade cached ASSERTED claims to VERIFIED when satellite imagery shows the asset got built.

The satellite sibling of `verifyclaims.py`. Same cache, same fields, same effect on the
score — imagery is simply another independent corroborator, so a matched claim moves from
CREDIT_ASSERTED to CREDIT_VERIFIED and its topic cap lifts from ASSERTED_TOPIC_CAP to 1.0.

THE GATE (this is the whole design). An observation verifies a SITE, not a CLAIM. Watching
one farm get built says nothing about a portfolio total, so a claim is only corroborated when
all three hold:

  1. the claim's SASB topic is one this asset class can speak to (a gas plant never
     corroborates an energy-transition claim);
  2. the claim actually names that asset class or that site;
  3. the claim is not a portfolio aggregate ("3.8 GW across the group").

Without (3) a single observed farm would inflate a group-wide number, which is the one way
this feature could make the engine worse than it was.

Absence never costs anything: an UNCHANGED or INCONCLUSIVE observation leaves the claim
exactly as it was. Cloud, a stale registry outline and phased construction all look
identical to "they did not build it".

    python -m backend.data.satverify              # all demo companies
    python -m backend.data.satverify U96 BN4      # specific companies
"""
from __future__ import annotations

import json
import re
import sys

from backend.data.realclaims import cache_path_for, cached_claims_for
from backend.engine import config, ingest
from backend.engine.satellite import (
    FOSSIL, RENEWABLE, STORAGE, company_sites, observation_payload, observe,
)

CORROBORATION_SOURCE = "Sentinel-2 / OpenStreetMap"

# --- the gate ---------------------------------------------------------------------
# asset class -> the SASB topics it is allowed to corroborate
TOPIC_GATE: dict[str, set[str]] = {
    "energy_transition": RENEWABLE | STORAGE,
    "energy_management": RENEWABLE | FOSSIL | STORAGE,
}

# words that identify the asset class in prose
ASSET_WORDS: dict[str, set[str]] = {
    "solar": {"solar", "photovoltaic", "pv"},
    "wind": {"wind", "turbine", "windfarm"},
    "hydro": {"hydro", "hydroelectric"},
    "biomass": {"biomass", "bioenergy"},
    "waste": {"waste-to-energy", "waste to energy", "energy-from-waste", "efw"},
    "battery": {"battery", "storage", "bess"},
    "coal": {"coal"},
    "gas": {"gas", "cogen", "combined cycle"},
}

# too generic to identify a site by
_STOPWORDS = {"power", "plant", "station", "energy", "farm", "limited", "ltd", "the",
              "and", "for", "solar", "wind", "gas", "coal", "floating", "phase",
              "system", "storage", "holdings", "international", "industries"}

# A claim must assert that something was BUILT or is OPERATING. Without this, prose like
# "committed to advance the solar industry" matches on the word "solar" and a training
# programme gets corroborated by a power station.
_BUILD_WORDS = ("built", "build", "constructed", "construction of", "commissioned",
                "completed", "operational", "in operation", "operates", "operating",
                "installed", "installation of", "opened", "came online", "energised",
                "energized", "located at", "located in", "owns", "acquired",
                "brought online", "began operations", "started operations")

# a claim at group/portfolio scale cannot be settled by looking at one asset
_AGGREGATE = ("portfolio", "globally", "group-wide", "group wide", "across our",
              "across the group", "aggregate", "combined capacity", "total capacity",
              "worldwide", "in total")
_GW = re.compile(r"\b\d+(?:\.\d+)?\s*gw\b", re.I)


def is_portfolio_aggregate(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _AGGREGATE) or bool(_GW.search(text))


def asserts_construction(text: str) -> bool:
    """True when the claim says an asset exists or was built, not merely that the company
    cares about the topic."""
    low = text.lower()
    return any(word in low for word in _BUILD_WORDS)


def _site_tokens(site_name: str | None, company_name: str) -> set[str]:
    """Distinctive place tokens from a site name.

    The company's own name is stripped: 'Sembcorp' appears in almost every claim that
    company makes, so leaving it in matches everything.
    """
    company_tokens = {t.lower() for t in re.split(r"[^A-Za-z0-9]+", company_name) if t}
    tokens = set()
    for token in re.split(r"[^A-Za-z0-9]+", site_name or ""):
        low = token.lower()
        if len(token) >= 5 and low not in _STOPWORDS and low not in company_tokens:
            tokens.add(low)
    return tokens


def claim_names_site(text: str, asset_type: str | None, site_name: str | None,
                     company_name: str) -> bool:
    """True when the prose points at this asset class or this specific place."""
    low = text.lower()
    if any(word in low for word in ASSET_WORDS.get((asset_type or "").lower(), set())):
        return True
    return any(token in low for token in _site_tokens(site_name, company_name))


def observation_supports(row: dict, obs, company_name: str) -> bool:
    """Whether this observation is allowed to corroborate this claim. All four must hold."""
    if obs.changed is not True:
        return False                      # only a positive observation ever counts
    asset_type = (obs.site.asset_type or "").lower()
    if asset_type not in TOPIC_GATE.get(str(row.get("topic_id") or ""), set()):
        return False
    text = str(row.get("text") or "")
    if is_portfolio_aggregate(text):
        return False
    if not asserts_construction(text):
        return False
    return claim_names_site(text, asset_type, obs.site.name, company_name)


# --- evidence payload --------------------------------------------------------------
def _evidence(obs) -> dict:
    """Flatten the shared observation payload onto the claim row, so the claims table can
    render the proof without a second round trip."""
    site = obs.site
    full = observation_payload(obs)
    return {
        "site_id": site.site_id,
        "site_name": site.name,
        "asset_type": site.asset_type,
        "lat": site.lat,
        "lon": site.lon,
        "operator": site.operator,
        "registry_url": site.registry_url,
        "index": obs.index,
        "change_score": obs.change_score,
        "note": obs.note,
        "before": full.get("before"),
        "after": full.get("after"),
        "detail_image": full.get("detail_image"),
        "detail_attribution": full.get("detail_attribution"),
        "map_links": full.get("map_links"),
    }


# --- per company -------------------------------------------------------------------
def verify_company(cid: str, ds, before_year: int, after_year: int,
                   limit: int, refresh: bool) -> int:
    name = ds.company(cid).name
    payload = cached_claims_for(cid, year=config.END_YEAR)
    if not payload:
        print(f"  {cid:4} {name:24} SKIP (no cached claims)")
        return 0
    rows = payload["claims"]

    # company_sites already orders renewables and storage first
    usable = sorted(set().union(*TOPIC_GATE.values()))
    sites = company_sites(cid, name, limit=limit, asset_types=usable)
    if not sites:
        print(f"  {cid:4} {name:24} no locatable assets")
        return 0

    observations = [observe(s, before_year, after_year, refresh=refresh) for s in sites]
    confirmed = [o for o in observations if o.changed is True]

    upgraded, changed = 0, False
    for row in rows:
        state = row.get("state")
        already_satellite = row.get("corroboration_source") == CORROBORATION_SOURCE
        # never overwrite a news corroboration; only ASSERTED rows and our own upgrades
        if state == "VERIFIED" and not already_satellite:
            continue
        if state not in ("ASSERTED", "VERIFIED"):
            continue

        match = next((o for o in confirmed if observation_supports(row, o, name)), None)
        if match:
            row["state"] = "VERIFIED"
            row["corroboration_url"] = match.site.registry_url
            row["corroboration_source"] = CORROBORATION_SOURCE
            row["satellite"] = _evidence(match)
            upgraded += 1
            changed = True
        elif already_satellite:
            # a previous satellite upgrade no longer holds -> release it, do not penalise
            row["state"] = "ASSERTED"
            for key in ("corroboration_url", "corroboration_source", "satellite"):
                row.pop(key, None)
            changed = True

    if changed:
        _save(cid, rows, payload)
    observed = len(confirmed)
    print(f"  {cid:4} {name:24} {observed} asset(s) observed built -> "
          f"{upgraded} claim(s) satellite-verified")
    return upgraded


def _save(cid: str, rows: list[dict], payload: dict) -> None:
    """Same write-back as verifyclaims: refresh the claims cache, then the company JSON."""
    (config.CACHE_DIR / "realclaims").mkdir(parents=True, exist_ok=True)
    cache_path_for(cid, config.END_YEAR).write_text(
        json.dumps({"rows": rows, "report_year": payload.get("report_year"),
                    "source_url": payload.get("source_url"),
                    "source_title": payload.get("source_title")}, ensure_ascii=False, indent=2),
        "utf-8")

    out = config.OUT_DIR / "company" / f"{cid}.json"
    if out.exists():
        data = json.loads(out.read_text("utf-8"))
        absent = data.get("claims", {}).get("absent", [])
        data["claims"] = cached_claims_for(cid, absent=absent, year=config.END_YEAR)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("companies", nargs="*", help="company ids (default: all demo companies)")
    ap.add_argument("--before", type=int, default=2019)
    ap.add_argument("--after", type=int, default=config.END_YEAR)
    ap.add_argument("--limit", type=int, default=8, help="max sites per company")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    ds = ingest.load()
    cids = args.companies or ds.demo_ids()
    print(f"satellite verification {args.before} -> {args.after}\n")
    total = sum(verify_company(cid, ds, args.before, args.after, args.limit, args.refresh)
                for cid in cids)
    print(f"\n{total} claim(s) upgraded to VERIFIED by imagery")
    return 0


if __name__ == "__main__":
    sys.exit(main())
