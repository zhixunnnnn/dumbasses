"""satellite — look at a site before and after a claimed build, and say what we saw.

Per site: pick the least-cloudy Sentinel-2 L2A scene in each window (Element84 Earth Search
STAC over AWS open data), render the same bbox for both through TiTiler, then run a
difference-in-differences on a spectral index:

    DiD = (index_after - index_before) ON the asset footprint
        - (index_after - index_before) in the surrounding control area

The control leg cancels season, sun angle, haze and regional drift. A raw brightness delta
cannot do that, and in a busy industrial area it reads a finished solar farm as UNCHANGED
because the neighbours were building too.

Two indices are computed and the stronger signal wins:
    NDWI = (green - nir) / (green + nir)   water cover  -> catches build-over-water
    NDVI = (nir - red)   / (nir + red)     vegetation   -> catches build-over-land

Two rules keep this honest:
  * `changed=None` (INCONCLUSIVE) is the default. No scene, too much cloud, or an ambiguous
    metric never becomes a verdict.
  * A negative observation is "we could not observe it", never "the company lied". Pixels
    do not support that claim and saying so is defamation-adjacent.

    python -m backend.engine.satellite --company U96 --before 2019 --after 2023 --type solar
"""
from __future__ import annotations

import json
import math
from io import BytesIO
from typing import Optional

import numpy as np
import requests
from PIL import Image, ImageDraw

from . import config
from .models import AssetSite, SiteObservation, SiteScene

_IMG_DIR = config.OUT_DIR / "satellite"

BBox = tuple[float, float, float, float]      # (min_lon, min_lat, max_lon, max_lat)

# Asset classes, shared with backend/data/satverify.py so the panel and the score agree.
RENEWABLE = {"solar", "wind", "hydro", "biomass", "waste", "geothermal", "tidal"}
FOSSIL = {"coal", "gas", "oil", "diesel", "nuclear"}
STORAGE = {"battery"}


# --- scene selection ---------------------------------------------------------------
def _search_scenes(lon: float, lat: float, year: int) -> list[dict]:
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
        "limit": 100,
    }
    resp = requests.post(config.STAC_SEARCH_URL, json=body, timeout=60)
    resp.raise_for_status()
    return resp.json().get("features", [])


def _cloud(feature: dict) -> float:
    value = feature.get("properties", {}).get("eo:cloud_cover")
    return 100.0 if value is None else float(value)


def best_scene(lon: float, lat: float, year: int) -> Optional[dict]:
    """Least-cloudy acquisition in `year`, or None if nothing clears the cloud gate."""
    try:
        feats = _search_scenes(lon, lat, year)
    except Exception:
        return None
    usable = [f for f in feats if _cloud(f) < config.SAT_MAX_CLOUD]
    if not usable:
        return None
    return min(usable, key=_cloud)


# --- framing and masking -----------------------------------------------------------
def site_bbox(site: AssetSite) -> BBox:
    """Frame the asset with room around it for a control area.

    Derived from the real footprint where OSM has one. A fixed box centred on the
    centroid lets a large or off-centre asset spill into the control region.
    """
    if site.footprint:
        lats = [p[0] for p in site.footprint]
        lons = [p[1] for p in site.footprint]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        pad_lat = max((max_lat - min_lat) * config.SAT_BBOX_PAD, config.SAT_BBOX_MIN_HALF)
        pad_lon = max((max_lon - min_lon) * config.SAT_BBOX_PAD, config.SAT_BBOX_MIN_HALF)
        return _squared(min_lon - pad_lon, min_lat - pad_lat,
                        max_lon + pad_lon, max_lat + pad_lat)
    half = config.SAT_BBOX_HALF_DEG
    return _squared(site.lon - half, site.lat - half, site.lon + half, site.lat + half)


def _squared(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> BBox:
    """Grow the shorter side so the box is square ON THE GROUND.

    Everything downstream renders into a square canvas, so a tall, narrow bbox would come
    back visibly squashed. A degree of longitude is shorter than a degree of latitude away
    from the equator, hence the cos(lat) term."""
    mid_lat = (min_lat + max_lat) / 2
    scale = max(math.cos(math.radians(mid_lat)), 0.01)
    height = max_lat - min_lat
    width = (max_lon - min_lon) * scale            # ground width, in latitude-equivalent degrees
    side = max(height, width)
    half_lat = side / 2
    half_lon = side / 2 / scale
    c_lat, c_lon = mid_lat, (min_lon + max_lon) / 2
    return (c_lon - half_lon, c_lat - half_lat, c_lon + half_lon, c_lat + half_lat)


def footprint_mask(site: AssetSite, bbox: BBox, px: int) -> Optional[np.ndarray]:
    """Rasterize the asset outline onto the rendered grid.

    Returns an int array: 1 = on the asset, 0 = control, -1 = buffer band along the
    edge (excluded from both, so georeferencing slop at the boundary cannot leak).
    None when there is no usable outline, which makes the site unmeasurable.
    """
    if len(site.footprint) < 3:
        return None
    min_lon, min_lat, max_lon, max_lat = bbox
    span_lon, span_lat = max_lon - min_lon, max_lat - min_lat
    if span_lon <= 0 or span_lat <= 0:
        return None

    # row 0 is north, so latitude is flipped
    pts = [((p[1] - min_lon) / span_lon * (px - 1),
            (max_lat - p[0]) / span_lat * (px - 1)) for p in site.footprint]

    inside = Image.new("L", (px, px), 0)
    ImageDraw.Draw(inside).polygon(pts, fill=1)
    band = Image.new("L", (px, px), 0)
    ImageDraw.Draw(band).line(pts + [pts[0]], fill=1,
                              width=max(2, int(px * config.SAT_EDGE_BUFFER)))

    mask = np.asarray(inside, dtype=np.int8).copy()
    mask[np.asarray(band, dtype=bool)] = -1
    if not (mask == 1).any() or not (mask == 0).any():
        return None
    return mask


# --- rendering ----------------------------------------------------------------------
def _bbox_url(bbox: BBox) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    px = config.SAT_IMAGE_PX
    return f"{config.TITILER_URL}/stac/bbox/{min_lon},{min_lat},{max_lon},{max_lat}/{px}x{px}.png"


def _fetch(scene: dict, bbox: BBox, assets: list[str], rescale: str) -> Optional[bytes]:
    params = {"url": f"{config.STAC_ITEM_URL}/{scene['id']}",
              "assets": assets, "rescale": rescale}
    try:
        resp = requests.get(_bbox_url(bbox), params=params, timeout=180)
        resp.raise_for_status()
        if "png" not in (resp.headers.get("content-type") or ""):
            return None
        return resp.content
    except Exception:
        return None


def render(scene: dict, bbox: BBox, out_path) -> bool:
    """True-colour crop for the UI. Same bbox for both dates, so they overlay exactly."""
    png = _fetch(scene, bbox, ["red", "green", "blue"], config.SAT_RESCALE)
    if png is None:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png)
    return True


def scene_indices(scene: dict, bbox: BBox) -> Optional[dict[str, np.ndarray]]:
    """NDWI and NDVI over the bbox, from one red/green/nir render.

    Packing three bands into one RGB request keeps this to a single fetch per scene. All
    bands share one linear stretch, so the normalized ratios stay valid.
    """
    png = _fetch(scene, bbox, ["red", "green", "nir"], config.SAT_BAND_RESCALE)
    if png is None:
        return None
    try:
        arr = np.asarray(Image.open(BytesIO(png)).convert("RGB"), dtype=np.float64)
    except Exception:
        return None
    red, green, nir = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return {
        "ndwi": (green - nir) / np.maximum(green + nir, 1e-6),
        "ndvi": (nir - red) / np.maximum(nir + red, 1e-6),
    }


# --- change detection ---------------------------------------------------------------
def difference_in_differences(before: np.ndarray, after: np.ndarray,
                              mask: np.ndarray) -> Optional[tuple[float, float]]:
    """(DiD, site_delta) — how far the index moved on the asset net of its surroundings,
    and how far it moved on the asset at all.

    Both matter. A large DiD driven purely by the NEIGHBOURS changing while the asset sat
    still is not construction here, so callers gate on `site_delta` as well.
    """
    if before.shape != after.shape or before.shape != mask.shape:
        return None
    on, control = mask == 1, mask == 0
    if not on.any() or not control.any():
        return None
    site_delta = float(after[on].mean() - before[on].mean())
    control_delta = float(after[control].mean() - before[control].mean())
    return site_delta - control_delta, site_delta


def strongest_signal(before: dict[str, np.ndarray], after: dict[str, np.ndarray],
                     mask: np.ndarray) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """(index name, DiD, site_delta) for whichever index moved most — water for
    build-over-water, vegetation for build-over-land. We do not know the prior land
    cover, so we try both."""
    best: tuple[Optional[str], Optional[float], Optional[float]] = (None, None, None)
    for name in ("ndwi", "ndvi"):
        if name not in before or name not in after:
            continue
        result = difference_in_differences(before[name], after[name], mask)
        if result is None:
            continue
        did, site_delta = result
        if best[1] is None or abs(did) > abs(best[1]):
            best = (name, did, site_delta)
    return best


_INDEX_LABEL = {"ndwi": "water cover", "ndvi": "vegetation cover"}


def _verdict(index: Optional[str], did: Optional[float],
             site_delta: Optional[float]) -> tuple[Optional[bool], str]:
    if index is None or did is None or site_delta is None:
        return None, "No comparable imagery — treated as inconclusive, not as a negative."
    label = _INDEX_LABEL.get(index, index)

    # The asset itself has to have changed. Otherwise a large DiD just means the
    # NEIGHBOURS built something, which says nothing about this site.
    if abs(site_delta) < config.SAT_MIN_SITE_DELTA:
        return False, (f"On-site {label} barely moved ({site_delta:+.2f}). No construction "
                       f"observed — this is not evidence the claim is false.")
    if abs(did) >= config.SAT_DID_CHANGED:
        direction = "fell" if did < 0 else "rose"
        return True, (f"On-site {label} {direction} by {abs(did):.2f} more than the "
                      f"surrounding area over the same period — consistent with "
                      f"construction here.")
    if abs(did) <= config.SAT_DID_UNCHANGED:
        return False, (f"On-site {label} tracked its surroundings ({did:+.2f}), so the shift "
                       f"looks regional. No construction observed — this is not evidence "
                       f"the claim is false.")
    return None, (f"On-site {label} moved {did:+.2f} against its surroundings, between the "
                  f"decision thresholds; inconclusive.")


# --- orchestration ------------------------------------------------------------------
def cached_observation(site: AssetSite, before_year: int,
                       after_year: int) -> Optional[SiteObservation]:
    """A previously computed observation, or None. Never touches the network.

    Fetching a site costs four renders, so the page reads what a batch run already
    produced rather than blocking on imagery — the same precompute-then-serve shape the
    rest of the engine uses.
    """
    meta_path = _IMG_DIR / f"{site.site_id}_{before_year}_{after_year}.json"
    if not meta_path.exists():
        return None
    try:
        return SiteObservation(**json.loads(meta_path.read_text("utf-8")))
    except Exception:
        return None


def observe(site: AssetSite, before_year: int, after_year: int,
            refresh: bool = False) -> SiteObservation:
    """Before/after look at one site. Always returns an observation; may be inconclusive."""
    _IMG_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = _IMG_DIR / f"{site.site_id}_{before_year}_{after_year}.json"
    if not refresh and meta_path.exists():
        try:
            return SiteObservation(**json.loads(meta_path.read_text("utf-8")))
        except Exception:
            pass

    bbox = site_bbox(site)
    mask = footprint_mask(site, bbox, config.SAT_IMAGE_PX)

    scenes: dict[str, Optional[SiteScene]] = {}
    indices: dict[str, Optional[dict]] = {}
    for label, year in (("before", before_year), ("after", after_year)):
        found = best_scene(site.lon, site.lat, year)
        if not found:
            scenes[label], indices[label] = None, None
            continue
        rel = f"satellite/{site.site_id}_{year}.png"
        ok = render(found, bbox, config.OUT_DIR / rel)
        scenes[label] = SiteScene(
            scene_id=found["id"], date=found["properties"]["datetime"][:10],
            cloud_cover=_cloud(found), image_path=rel if ok else None)
        indices[label] = scene_indices(found, bbox) if mask is not None else None

    before, after = scenes.get("before"), scenes.get("after")
    index_name = did = site_delta = None
    if indices.get("before") and indices.get("after") and mask is not None:
        index_name, did, site_delta = strongest_signal(
            indices["before"], indices["after"], mask)

    changed, note = _verdict(index_name, did, site_delta)
    if not (before and after):
        missing = "the baseline year" if not before else "the comparison year"
        note = f"No low-cloud Sentinel-2 scene for {missing}; inconclusive."
    elif mask is None:
        note = ("No outline for this asset in the registry, only a point — there is no "
                "footprint to measure against its surroundings; inconclusive.")

    obs = SiteObservation(site=site, before=before, after=after, index=index_name,
                          change_score=did, changed=changed, note=note)
    meta_path.write_text(json.dumps(obs.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    return obs


def observation_payload(obs: SiteObservation, with_detail: bool = True) -> dict:
    """Everything a reader needs to check the asset themselves.

    Sentinel-2 supplies the dated before/after that decides the verdict; the high-resolution
    basemap and the third-party map links exist so a human can confirm the thing is really
    there, in a viewer we do not control.
    """
    from .basemap import detail_image, map_links

    site = obs.site
    rel_detail = f"satellite/{site.site_id}_detail.jpg"
    attribution = None
    if with_detail:
        meta = detail_image(site, site_bbox(site), config.OUT_DIR / rel_detail)
        attribution = (meta or {}).get("attribution")
    has_detail = (config.OUT_DIR / rel_detail).exists()

    payload = obs.model_dump()
    payload["detail_image"] = rel_detail if has_detail else None
    payload["detail_attribution"] = attribution
    payload["map_links"] = map_links(site)
    return payload


def company_sites(company_id: str, company_name: str, limit: int = 6,
                  asset_types: Optional[list[str]] = None,
                  refresh: bool = False, offline: bool = False) -> list[AssetSite]:
    """This company's registry sites, optionally narrowed to an asset class (a claim about
    wind farms should not be answered with a gas plant).

    `offline` reads the site cache only. Read paths — the API, the chat tool — pass it so a
    company nobody has geolocated yet returns empty instead of blocking on Overpass.
    """
    from .geolocate import find_sites

    sites = find_sites(company_id, company_name, refresh=refresh, offline=offline)
    if asset_types:
        wanted = {t.lower() for t in asset_types}
        sites = [s for s in sites if (s.asset_type or "").lower() in wanted]
    # Renewables and storage first. These are the classes companies actually make
    # build-claims about, and a plain alphabetical cut spends the limit on gas plants —
    # which once hid the only asset in the set that had visibly been built.
    sites.sort(key=lambda s: (0 if (s.asset_type or "").lower() in RENEWABLE | STORAGE else 1,
                              s.name or ""))
    return sites[:limit]


def observe_company(company_id: str, company_name: str, before_year: int, after_year: int,
                    limit: int = 6, asset_types: Optional[list[str]] = None,
                    refresh: bool = False,
                    cached_only: bool = False) -> list[SiteObservation]:
    """Observations for this company's sites.

    `cached_only` returns just what a batch run already computed, so a page load never
    waits on the imagery services — nor on the registry lookup behind them.
    """
    sites = company_sites(company_id, company_name, limit, asset_types, refresh,
                          offline=cached_only)
    if cached_only:
        found = (cached_observation(s, before_year, after_year) for s in sites)
        return [o for o in found if o is not None]
    return [observe(s, before_year, after_year, refresh=refresh) for s in sites]


def main() -> None:
    import argparse

    from . import ingest

    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--before", type=int, default=2019)
    ap.add_argument("--after", type=int, default=config.END_YEAR)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--type", default=None, help="comma-separated asset types, e.g. solar,wind")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    ds = ingest.load()
    comp = ds.company(args.company)
    types = [t.strip() for t in args.type.split(",")] if args.type else None
    obs = observe_company(comp.company_id, comp.name, args.before, args.after,
                          limit=args.limit, asset_types=types, refresh=args.refresh)

    print(f"{comp.name}: {len(obs)} site(s) observed {args.before} -> {args.after}\n")
    labels = {True: "CHANGED", False: "UNCHANGED", None: "INCONCLUSIVE"}
    for o in obs:
        score = f"{o.change_score:+.3f}" if o.change_score is not None else "   n/a"
        print(f"  {labels[o.changed]:13} {score:>7} {o.index or '    ':5} "
              f"{o.site.asset_type or '?':7} {o.site.name or '(unnamed)'}")
        for lbl, sc in (("before", o.before), ("after", o.after)):
            if sc:
                print(f"      {lbl:6} {sc.date}  cloud={sc.cloud_cover:.1f}%  {sc.image_path}")
        print(f"      {o.note}")


if __name__ == "__main__":
    main()
