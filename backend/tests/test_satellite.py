"""Satellite verification guardrails — offline, no network.

The point of these tests is the honesty contract, not the imagery:
  * a verdict is only ever CHANGED / UNCHANGED / INCONCLUSIVE, and INCONCLUSIVE is default
  * a whole-frame shift (season, haze, sun angle) must NOT read as construction
  * coordinates only ever come from a citable registry row
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.engine import config, satellite
from backend.engine.geolocate import _confidence, search_terms
from backend.engine.models import AssetSite


# ---- geolocation -----------------------------------------------------------------
def test_search_terms_drop_corporate_suffixes():
    assert search_terms("Sembcorp Industries") == ["Sembcorp"]
    assert search_terms("Wilmar International") == ["Wilmar"]


def test_search_terms_keep_short_lead_token_as_phrase_only():
    # 'City' alone is far too generic to query OSM with; the phrase must survive instead
    terms = search_terms("City Developments Ltd")
    assert "City Developments" in terms
    assert "City" not in terms


def test_operator_match_outranks_name_match():
    operator_hit = _confidence({"operator": "Sembcorp Solar", "name": "Tengeh"}, ["Sembcorp"])
    name_hit = _confidence({"operator": "Other Co", "name": "Sembcorp Cogen"}, ["Sembcorp"])
    assert operator_hit > name_hit
    assert _confidence({"operator": "Unrelated", "name": "Unrelated"}, ["Sembcorp"]) == 0.0


def test_weak_matches_are_below_the_admission_threshold():
    assert _confidence({"name": "Unrelated"}, ["Sembcorp"]) < config.SAT_MIN_MATCH_CONF


def test_empty_registry_result_is_never_cached(tmp_path, monkeypatch):
    """A transient Overpass outage must not freeze into a permanent 'owns nothing'."""
    from backend.engine import geolocate

    monkeypatch.setattr(geolocate, "_cache_path", lambda cid: tmp_path / f"{cid}.json")
    monkeypatch.setattr(geolocate, "_overpass_one", lambda *a, **k: [])
    assert geolocate.find_sites("U96", "Sembcorp Industries") == []
    assert not (tmp_path / "U96.json").exists()


def test_stale_mirror_empty_response_falls_through(monkeypatch):
    """A mirror answering 200-with-zero-elements must not win over a healthy mirror."""
    from backend.engine import geolocate

    real = [{"type": "way", "id": 1, "tags": {"operator": "Sembcorp", "name": "X"},
             "center": {"lat": 1.0, "lon": 103.0}}]
    calls = {"n": 0}

    class Resp:
        def __init__(self, payload): self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p

    def fake_post(url, **_k):
        calls["n"] += 1
        return Resp({"elements": []}) if calls["n"] == 1 else Resp({"elements": real})

    monkeypatch.setattr(geolocate.requests, "post", fake_post)
    assert geolocate._overpass_one("operator", "Sembcorp") == real


def test_all_mirrors_empty_means_genuinely_no_match(monkeypatch):
    from backend.engine import geolocate

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"elements": []}

    monkeypatch.setattr(geolocate.requests, "post", lambda *a, **k: Resp())
    assert geolocate._overpass_one("operator", "Nonexistent") == []


# ---- framing and masking ---------------------------------------------------------
def _site(**kw):
    base = dict(site_id="s1", company_id="U96", lat=1.35, lon=103.645,
                registry_url="https://www.openstreetmap.org/way/1", match_confidence=0.9)
    base.update(kw)
    return AssetSite(**base)


_SQUARE = [[1.340, 103.640], [1.340, 103.651], [1.355, 103.651], [1.355, 103.640]]


def test_bbox_is_derived_from_the_footprint_not_the_centroid():
    min_lon, min_lat, max_lon, max_lat = satellite.site_bbox(_site(footprint=_SQUARE))
    assert min_lat < 1.340 and max_lat > 1.355
    assert min_lon < 103.640 and max_lon > 103.651


def test_bbox_falls_back_to_a_fixed_box_without_a_footprint():
    """No outline -> a fixed box centred on the point, still squared for the canvas."""
    site = _site(footprint=[])
    min_lon, min_lat, max_lon, max_lat = satellite.site_bbox(site)
    assert (min_lat + max_lat) / 2 == pytest.approx(site.lat)
    assert (min_lon + max_lon) / 2 == pytest.approx(site.lon)
    assert (max_lat - min_lat) / 2 == pytest.approx(config.SAT_BBOX_HALF_DEG, rel=0.01)


def test_mask_marks_asset_control_and_buffer():
    site = _site(footprint=_SQUARE)
    mask = satellite.footprint_mask(site, satellite.site_bbox(site), 128)
    assert mask is not None and mask.shape == (128, 128)
    assert (mask == 1).any(), "some pixels must land on the asset"
    assert (mask == 0).any(), "some pixels must remain as control"
    assert (mask == -1).any(), "the edge buffer must be excluded from both"
    assert mask[64, 64] == 1, "a padded frame puts the asset in the middle"


def test_mask_is_none_without_a_usable_outline():
    assert satellite.footprint_mask(_site(footprint=[]), (0, 0, 1, 1), 64) is None
    assert satellite.footprint_mask(
        _site(footprint=[[1.0, 103.0], [1.1, 103.1]]), (0, 0, 1, 1), 64) is None


# ---- difference-in-differences ---------------------------------------------------
def _mask(px=64):
    mask = np.zeros((px, px), dtype=np.int8)
    mask[8:28, 8:28] = 1          # asset sits off-centre on purpose
    return mask


def test_regional_drift_cancels_out():
    """Season/haze move the WHOLE frame. The control leg must subtract that to ~zero."""
    mask = _mask()
    before = np.full((64, 64), 0.5)
    after = before - 0.30         # everything drifts by the same amount
    did, site_delta = satellite.difference_in_differences(before, after, mask)
    assert abs(did) < 1e-9
    assert site_delta == pytest.approx(-0.30)
    assert satellite._verdict("ndwi", did, site_delta)[0] is False


def test_change_confined_to_the_asset_survives_the_control_leg():
    mask = _mask()
    before = np.full((64, 64), 0.5)
    after = before.copy()
    after[mask == 1] -= 0.4       # only the asset changes
    did, site_delta = satellite.difference_in_differences(before, after, mask)
    assert did == pytest.approx(-0.4)
    assert satellite._verdict("ndwi", did, site_delta)[0] is True


def test_offsite_construction_does_not_become_an_onsite_verdict():
    """Neighbours building must not be credited to this company's asset, even though it
    produces a large difference-in-differences."""
    mask = _mask()
    before = np.full((64, 64), 0.5)
    after = before.copy()
    after[mask == 0] -= 0.4       # the surroundings changed, the asset did not
    did, site_delta = satellite.difference_in_differences(before, after, mask)
    assert abs(did) >= config.SAT_DID_CHANGED, "DiD alone would say CHANGED"
    assert satellite._verdict("ndwi", did, site_delta)[0] is False, (
        "the site-delta gate must veto it")


def test_did_is_none_on_shape_mismatch():
    assert satellite.difference_in_differences(
        np.zeros((64, 64)), np.zeros((32, 32)), _mask()) is None


def test_did_is_none_without_both_regions():
    all_asset = np.ones((64, 64), dtype=np.int8)
    assert satellite.difference_in_differences(
        np.zeros((64, 64)), np.zeros((64, 64)), all_asset) is None


def test_strongest_signal_picks_the_larger_absolute_move():
    mask = _mask()
    flat = np.full((64, 64), 0.5)
    ndwi_after = flat.copy()
    ndwi_after[mask == 1] -= 0.40
    ndvi_after = flat.copy()
    ndvi_after[mask == 1] -= 0.05

    name, did, site_delta = satellite.strongest_signal(
        {"ndwi": flat, "ndvi": flat}, {"ndwi": ndwi_after, "ndvi": ndvi_after}, mask)
    assert name == "ndwi"
    assert did == pytest.approx(-0.40)
    assert site_delta == pytest.approx(-0.40)


# ---- verdicts --------------------------------------------------------------------
def test_missing_signal_is_inconclusive_not_negative():
    changed, note = satellite._verdict(None, None, None)
    assert changed is None
    assert "inconclusive" in note.lower()


def test_between_thresholds_is_inconclusive():
    midpoint = (config.SAT_DID_UNCHANGED + config.SAT_DID_CHANGED) / 2
    assert satellite._verdict("ndvi", midpoint, -0.5)[0] is None


def test_verdict_is_symmetric_in_direction():
    """A build can raise or lower an index depending on prior land cover."""
    big = config.SAT_DID_CHANGED + 0.1
    assert satellite._verdict("ndvi", big, big)[0] is True
    assert satellite._verdict("ndvi", -big, -big)[0] is True


def test_unchanged_verdict_never_calls_the_claim_false():
    changed, note = satellite._verdict("ndwi", 0.0, -0.5)
    assert changed is False
    assert "not evidence the claim is false" in note


# ---- scene selection / offline behaviour -----------------------------------------
def test_best_scene_returns_none_when_search_fails(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no network")
    monkeypatch.setattr(satellite, "_search_scenes", boom)
    assert satellite.best_scene(103.6, 1.3, 2019) is None


def test_cloudy_scenes_are_rejected(monkeypatch):
    monkeypatch.setattr(satellite, "_search_scenes", lambda *a, **k: [
        {"id": "cloudy", "properties": {"eo:cloud_cover": config.SAT_MAX_CLOUD + 10}},
        {"id": "missing", "properties": {}},
    ])
    assert satellite.best_scene(103.6, 1.3, 2019) is None


def test_least_cloudy_scene_wins(monkeypatch):
    monkeypatch.setattr(satellite, "_search_scenes", lambda *a, **k: [
        {"id": "hazy", "properties": {"eo:cloud_cover": 12.0}},
        {"id": "clear", "properties": {"eo:cloud_cover": 2.0}},
    ])
    assert satellite.best_scene(103.6, 1.3, 2019)["id"] == "clear"


def test_observe_without_imagery_is_inconclusive(monkeypatch, tmp_path):
    monkeypatch.setattr(satellite, "best_scene", lambda *a, **k: None)
    monkeypatch.setattr(satellite, "_IMG_DIR", tmp_path)

    obs = satellite.observe(_site(footprint=_SQUARE), 2019, 2023, refresh=True)
    assert obs.changed is None
    assert obs.before is None and obs.after is None
    assert obs.change_score is None
    assert "inconclusive" in obs.note.lower()


def test_point_only_site_is_inconclusive_not_measured(monkeypatch, tmp_path):
    """A registry point with no outline gives nothing to measure against its surroundings."""
    monkeypatch.setattr(satellite, "_IMG_DIR", tmp_path)
    monkeypatch.setattr(satellite, "best_scene", lambda *a, **k: {
        "id": "S2X", "properties": {"datetime": "2023-03-16T00:00:00Z", "eo:cloud_cover": 3.0}})
    monkeypatch.setattr(satellite, "render", lambda *a, **k: True)
    monkeypatch.setattr(satellite, "scene_indices", lambda *a, **k: None)

    obs = satellite.observe(_site(footprint=[]), 2019, 2023, refresh=True)
    assert obs.changed is None
    assert obs.change_score is None
    assert "no outline" in obs.note.lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
