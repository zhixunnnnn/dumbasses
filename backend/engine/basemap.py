"""basemap — a high-resolution look at a located asset, so a reader can check it themselves.

Sentinel-2 (10 m) is the right source for the dated before/after that drives the verdict,
but it is too coarse to recognise anything by eye. This module stitches Esri World Imagery
(sub-metre in most places) into one image and draws the registry outline on top, so what
was measured is visible rather than asserted.

Esri imagery carries no reliable capture date, so it is NEVER used for the verdict — only
to let a human confirm the asset is really there. Attribution is required and travels with
the payload.

    python -m backend.engine.basemap --company U96 --type solar
"""
from __future__ import annotations

import math
from io import BytesIO
from typing import Optional

import requests
from PIL import Image, ImageDraw

from . import config
from .models import AssetSite

TILE_PX = 256
ATTRIBUTION = "Esri, Maxar, Earthstar Geographics"


def _lonlat_to_px(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Web-Mercator pixel coordinates at this zoom."""
    n = TILE_PX * 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    s = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def _pick_zoom(bbox: tuple[float, float, float, float]) -> int:
    """Deepest zoom whose render stays under the pixel budget."""
    min_lon, _, max_lon, _ = bbox
    for zoom in range(config.BASEMAP_MAX_ZOOM, 5, -1):
        x0, _ = _lonlat_to_px(min_lon, 0, zoom)
        x1, _ = _lonlat_to_px(max_lon, 0, zoom)
        if (x1 - x0) <= config.BASEMAP_TARGET_PX:
            return zoom
    return 12


def _stitch(bbox: tuple[float, float, float, float],
            zoom: int) -> Optional[tuple[Image.Image, float, float]]:
    """(image, origin_x, origin_y) — tiles covering the bbox, cropped to it."""
    min_lon, min_lat, max_lon, max_lat = bbox
    x0, y0 = _lonlat_to_px(min_lon, max_lat, zoom)
    x1, y1 = _lonlat_to_px(max_lon, min_lat, zoom)
    tx0, ty0 = int(x0 // TILE_PX), int(y0 // TILE_PX)
    tx1, ty1 = int(x1 // TILE_PX), int(y1 // TILE_PX)

    tiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    if tiles > config.BASEMAP_MAX_TILES:
        return None

    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_PX, (ty1 - ty0 + 1) * TILE_PX))
    fetched = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            url = config.BASEMAP_TILE_URL.format(z=zoom, x=tx, y=ty)
            try:
                resp = requests.get(url, headers={"User-Agent": "polyfintech-esg-evidence-engine"},
                                    timeout=30)
                resp.raise_for_status()
                tile = Image.open(BytesIO(resp.content)).convert("RGB")
            except Exception:
                continue                      # a missing tile leaves a gap, not a failure
            canvas.paste(tile, ((tx - tx0) * TILE_PX, (ty - ty0) * TILE_PX))
            fetched += 1
    if not fetched:
        return None
    crop = canvas.crop((int(x0 - tx0 * TILE_PX), int(y0 - ty0 * TILE_PX),
                        int(x1 - tx0 * TILE_PX), int(y1 - ty0 * TILE_PX)))
    return crop, x0, y0


def detail_image(site: AssetSite, bbox: tuple[float, float, float, float],
                 out_path, refresh: bool = False) -> Optional[dict]:
    """Render the asset at high resolution with its registry outline drawn on.

    Returns {"zoom", "attribution"} on success, None if the basemap was unreachable.
    """
    if out_path.exists() and not refresh:
        return {"zoom": None, "attribution": ATTRIBUTION}

    zoom = _pick_zoom(bbox)
    stitched = _stitch(bbox, zoom)
    if stitched is None:
        return None
    image, origin_x, origin_y = stitched

    if len(site.footprint) >= 3:
        points = []
        for lat, lon in site.footprint:
            px, py = _lonlat_to_px(lon, lat, zoom)
            points.append((px - origin_x, py - origin_y))
        draw = ImageDraw.Draw(image, "RGBA")
        # a soft dark halo first, so the outline reads over bright and dark ground alike
        draw.line(points + [points[0]], fill=(0, 0, 0, 140), width=7)
        draw.line(points + [points[0]], fill=(255, 214, 0, 255), width=3)

    # Zoom is chosen for detail, then the delivered image is capped — a small asset at z18
    # would otherwise ship a 2200px, ~1 MB frame for a card rendered a few hundred px wide.
    cap = config.BASEMAP_OUTPUT_MAX_PX
    if max(image.size) > cap:
        image.thumbnail((cap, cap), Image.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # JPEG, not PNG: this is aerial photography, and a PNG of the same frame runs ~10x
    # the bytes, which is far too heavy for six cards on a dashboard panel.
    image.save(out_path, format="JPEG", quality=config.BASEMAP_JPEG_QUALITY, optimize=True,
               progressive=True)
    return {"zoom": zoom, "attribution": ATTRIBUTION}


def map_links(site: AssetSite) -> dict[str, str]:
    """Third-party viewers, so the reader can leave and check independently.

    Plain links only — no embedded Google tiles, which their terms do not allow.
    """
    lat, lon = site.lat, site.lon
    return {
        "google_maps": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
        "google_maps_satellite": f"https://www.google.com/maps/@{lat},{lon},17z/data=!3m1!1e3",
        "google_earth": f"https://earth.google.com/web/@{lat},{lon},0a,2000d,35y,0h,0t,0r",
        "openstreetmap": site.registry_url or f"https://www.openstreetmap.org/#map=16/{lat}/{lon}",
    }


def main() -> None:
    import argparse

    from . import ingest
    from .geolocate import find_sites
    from .satellite import site_bbox

    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--type", default=None, help="comma-separated asset types")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    comp = ingest.load().company(args.company)
    sites = find_sites(comp.company_id, comp.name)
    if args.type:
        wanted = {t.strip().lower() for t in args.type.split(",")}
        sites = [s for s in sites if (s.asset_type or "").lower() in wanted]

    for site in sites[:args.limit]:
        rel = f"satellite/{site.site_id}_detail.jpg"
        meta = detail_image(site, site_bbox(site), config.OUT_DIR / rel, refresh=args.refresh)
        status = f"z{meta['zoom']}" if meta and meta.get("zoom") else ("cached" if meta else "FAILED")
        print(f"  {status:8} {site.name or '(unnamed)':45} {rel}")


if __name__ == "__main__":
    main()
