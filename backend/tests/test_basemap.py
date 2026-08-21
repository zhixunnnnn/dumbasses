"""High-resolution basemap: framing, outlining and the links that let a reader leave.

Offline — no tiles are fetched. What is checked here is the geometry and the promises the
UI makes about it.
"""
from __future__ import annotations

import math

import pytest

from backend.engine import basemap, config, satellite
from backend.engine.models import AssetSite

SQUARE = [[1.340, 103.640], [1.340, 103.651], [1.355, 103.651], [1.355, 103.640]]
TALL = [[1.330, 103.645], [1.330, 103.648], [1.380, 103.648], [1.380, 103.645]]


def _site(**kw):
    base = dict(site_id="s1", company_id="U96", lat=1.35, lon=103.645,
                registry_url="https://www.openstreetmap.org/way/979479451",
                match_confidence=0.9)
    base.update(kw)
    return AssetSite(**base)


# ---- framing ---------------------------------------------------------------------
def _ground_aspect(bbox):
    min_lon, min_lat, max_lon, max_lat = bbox
    scale = math.cos(math.radians((min_lat + max_lat) / 2))
    return ((max_lon - min_lon) * scale) / (max_lat - min_lat)


@pytest.mark.parametrize("footprint", [SQUARE, TALL, []])
def test_bbox_is_square_on_the_ground(footprint):
    """Everything renders into a square canvas, so a tall asset would come back squashed."""
    bbox = satellite.site_bbox(_site(footprint=footprint))
    assert _ground_aspect(bbox) == pytest.approx(1.0, abs=0.01)


def test_bbox_still_contains_a_tall_footprint():
    bbox = satellite.site_bbox(_site(footprint=TALL))
    min_lon, min_lat, max_lon, max_lat = bbox
    assert min_lat < 1.330 and max_lat > 1.380
    assert min_lon < 103.645 and max_lon > 103.648


def test_square_bbox_holds_far_from_the_equator():
    """A degree of longitude is much shorter at high latitude; the cos(lat) term matters."""
    site = _site(lat=54.59, lon=-1.12,
                 footprint=[[54.58, -1.13], [54.58, -1.11], [54.60, -1.11], [54.60, -1.13]])
    assert _ground_aspect(satellite.site_bbox(site)) == pytest.approx(1.0, abs=0.01)


# ---- zoom ------------------------------------------------------------------------
def test_zoom_stays_within_the_pixel_budget():
    bbox = satellite.site_bbox(_site(footprint=SQUARE))
    zoom = basemap._pick_zoom(bbox)
    x0, _ = basemap._lonlat_to_px(bbox[0], 0, zoom)
    x1, _ = basemap._lonlat_to_px(bbox[2], 0, zoom)
    assert (x1 - x0) <= config.BASEMAP_TARGET_PX
    assert zoom <= config.BASEMAP_MAX_ZOOM


def test_a_smaller_asset_earns_a_deeper_zoom():
    tiny = [[1.3500, 103.6450], [1.3500, 103.6455], [1.3505, 103.6455], [1.3505, 103.6450]]
    big = basemap._pick_zoom(satellite.site_bbox(_site(footprint=SQUARE)))
    small = basemap._pick_zoom(satellite.site_bbox(_site(footprint=tiny)))
    assert small > big


def test_absurd_stitches_are_refused_not_attempted():
    """Guard against hammering the tile server for a whole-country bbox."""
    assert basemap._stitch((-180.0, -85.0, 180.0, 85.0), 12) is None


# ---- projection ------------------------------------------------------------------
def test_pixel_projection_is_monotonic():
    """Longitude grows east, pixel-y grows south — the outline depends on both."""
    x_west, _ = basemap._lonlat_to_px(103.60, 1.35, 16)
    x_east, _ = basemap._lonlat_to_px(103.70, 1.35, 16)
    _, y_north = basemap._lonlat_to_px(103.65, 1.40, 16)
    _, y_south = basemap._lonlat_to_px(103.65, 1.30, 16)
    assert x_east > x_west
    assert y_south > y_north


def test_projection_survives_the_poles():
    for lat in (89.9999, -89.9999):
        _, y = basemap._lonlat_to_px(0.0, lat, 10)
        assert math.isfinite(y)


# ---- links -----------------------------------------------------------------------
def test_map_links_point_at_the_asset():
    site = _site()
    links = basemap.map_links(site)
    for key in ("google_maps", "google_maps_satellite", "google_earth", "openstreetmap"):
        assert key in links
    assert "1.35" in links["google_maps"] and "103.645" in links["google_maps"]
    assert links["openstreetmap"] == site.registry_url


def test_map_links_fall_back_without_a_registry_url():
    links = basemap.map_links(_site(registry_url=None))
    assert links["openstreetmap"].startswith("https://www.openstreetmap.org/")


# ---- cache -----------------------------------------------------------------------
def test_cached_observation_is_none_when_nothing_was_computed(monkeypatch, tmp_path):
    monkeypatch.setattr(satellite, "_IMG_DIR", tmp_path)
    assert satellite.cached_observation(_site(footprint=SQUARE), 2019, 2024) is None


def test_cached_observation_never_hits_the_network(monkeypatch, tmp_path):
    """A page load must not be able to trigger imagery fetches."""
    monkeypatch.setattr(satellite, "_IMG_DIR", tmp_path)

    def boom(*_a, **_k):
        raise AssertionError("cached_observation must not fetch")

    monkeypatch.setattr(satellite, "best_scene", boom)
    monkeypatch.setattr(satellite, "_search_scenes", boom)
    assert satellite.cached_observation(_site(footprint=SQUARE), 2019, 2024) is None


def test_cached_observation_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(satellite, "_IMG_DIR", tmp_path)
    monkeypatch.setattr(satellite, "best_scene", lambda *a, **k: None)
    site = _site(footprint=SQUARE)

    written = satellite.observe(site, 2019, 2024, refresh=True)
    restored = satellite.cached_observation(site, 2019, 2024)
    assert restored is not None
    assert restored.site.site_id == written.site.site_id
    assert restored.changed is written.changed
