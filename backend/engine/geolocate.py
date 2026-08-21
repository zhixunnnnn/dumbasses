"""geolocate — resolve a company to physical asset sites with citable coordinates.

Coordinates are NEVER produced by the model. They come from OpenStreetMap rows we can
link back to (guardrail T7: no fabricated numbers). A company with no registry match
yields an empty list, which downstream must treat as "could not locate" — never as a
penalty (the asymmetric specialist rule in verify.py).

    python -m backend.engine.geolocate --company U96
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

import requests

from . import config
from .models import AssetSite

# corporate suffixes that carry no search signal
_SUFFIX = {"ltd", "limited", "group", "holdings", "international", "industries",
           "investment", "investments", "corporation", "corp", "company", "co",
           "plc", "bhd", "pte", "inc", "sa", "nv", "ag"}

# Only whole plants. `power=generator` would also match every rooftop panel on earth,
# which times Overpass out and is noise for asset-level claims anyway.
_PLANT = '["power"="plant"]'

# Public Overpass mirrors, tried in order — the main instance rate-limits and 504s.
_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
)


def _cache_path(company_id: str):
    d = config.CACHE_DIR / "sites"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{company_id}.json"


def search_terms(company_name: str) -> list[str]:
    """Distinctive tokens to match against OSM operator/name tags.

    Drops corporate suffixes, keeps the remaining phrase, and adds the lead token only
    when it is long enough to be distinctive ('Sembcorp' yes, 'City' no)."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", company_name) if w]
    core = [w for w in words if w.lower() not in _SUFFIX]
    if not core:
        core = words
    terms = [" ".join(core)]
    if len(core) > 1 and len(core[0]) >= 6:
        terms.append(core[0])
    return terms


def _overpass_one(key: str, term: str, timeout: int = 60) -> list[dict]:
    """One tag-key regex scan. Kept as a SINGLE clause on purpose: unioning `operator`
    and `name` into one request reliably 504s the public mirrors.

    A mirror answering 200 with zero elements is treated as a FAILURE and we fall through
    to the next one — stale mirrors return empty successes, and silently accepting that
    would look identical to "this company owns nothing".
    """
    query = f'[out:json][timeout:25];nwr{_PLANT}["{key}"~"{term}",i];out geom tags;'
    urls = [config.OVERPASS_URL] + [m for m in _MIRRORS if m != config.OVERPASS_URL]
    saw_empty = False
    last: Exception | None = None
    for url in urls:
        try:
            resp = requests.post(url, data={"data": query},
                                 headers={"User-Agent": "polyfintech-esg-evidence-engine"},
                                 timeout=timeout)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            if elements:
                return elements
            saw_empty = True
        except Exception as exc:      # mirror down or rate-limited -> try the next
            last = exc
    if saw_empty:                     # every reachable mirror agreed: genuinely no match
        return []
    raise last if last else RuntimeError("no overpass mirror configured")


def _confidence(tags: dict, terms: list[str]) -> float:
    """Operator match is strong evidence of ownership; a bare name match is weaker."""
    operator = (tags.get("operator") or "").lower()
    name = (tags.get("name") or "").lower()
    for t in (x.lower() for x in terms):
        if t in operator:
            return 0.9
    for t in (x.lower() for x in terms):
        if t in name:
            return 0.6
    return 0.0


def _asset_type(tags: dict) -> Optional[str]:
    return tags.get("plant:source") or tags.get("generator:source") or None


def find_sites(company_id: str, company_name: str, refresh: bool = False,
               offline: bool = False) -> list[AssetSite]:
    """Registry rows for this company, best-match first. Empty list = could not locate.

    `refresh` bypasses the cache READ but still writes the fresh result — otherwise a
    refresh run would leave the cache empty for everyone downstream."""
    cache = _cache_path(company_id)
    if not refresh and cache.exists():
        cached = json.loads(cache.read_text("utf-8"))
        # An empty cached list is treated as a MISS, never as "this company has no assets" —
        # a transient mirror outage must not freeze into a permanent no-match.
        if cached.get("_name") == company_name and cached.get("sites"):
            return [AssetSite(**s) for s in cached["sites"]]
    if offline:
        return []

    terms = search_terms(company_name)
    elements: dict[tuple, dict] = {}
    for term in terms:
        for key in ("operator", "name"):
            try:
                for el in _overpass_one(key, term):
                    elements[(el.get("type"), el.get("id"))] = el
            except Exception:
                continue  # a dead mirror must not break the pipeline

    sites: list[AssetSite] = []
    for (osm_type, osm_id), el in elements.items():
        tags = el.get("tags") or {}
        # `out geom` returns the full outline for ways/relations; nodes carry a bare lat/lon.
        footprint = [[p["lat"], p["lon"]] for p in (el.get("geometry") or [])
                     if p.get("lat") is not None and p.get("lon") is not None]
        if footprint:
            lats = [p[0] for p in footprint]
            lons = [p[1] for p in footprint]
            lat, lon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        else:
            centre = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
            lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        conf = _confidence(tags, terms)
        if conf < config.SAT_MIN_MATCH_CONF:
            continue
        sites.append(AssetSite(
            site_id=hashlib.sha1(f"{osm_type}/{osm_id}".encode()).hexdigest()[:12],
            company_id=company_id,
            name=tags.get("name"),
            asset_type=_asset_type(tags),
            lat=float(lat), lon=float(lon),
            operator=tags.get("operator"),
            registry="openstreetmap",
            registry_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            match_confidence=conf,
            footprint=footprint,
        ))

    sites.sort(key=lambda s: (-s.match_confidence, s.name or ""))
    if sites:                            # only cache a positive result (see the read guard)
        cache.write_text(json.dumps(
            {"_name": company_name, "sites": [s.model_dump() for s in sites]},
            ensure_ascii=False, indent=2), "utf-8")
    return sites


def main() -> None:
    import argparse
    from . import ingest

    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = ap.parse_args()

    ds = ingest.load()
    comp = ds.company(args.company)
    sites = find_sites(comp.company_id, comp.name, refresh=args.refresh)
    print(f"{comp.name}: {len(sites)} site(s)  terms={search_terms(comp.name)}")
    for s in sites:
        print(f"  [{s.match_confidence:.1f}] {s.asset_type or '?':8} {s.name or '(unnamed)':45} "
              f"{s.lat:9.4f},{s.lon:9.4f}  {s.registry_url}")


if __name__ == "__main__":
    main()
