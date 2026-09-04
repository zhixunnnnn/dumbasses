"""Real Sustainalytics overlay: the committed values mark the channel REAL on their own
assessment year and write the risk value onto the RaterRow, without inventing coverage for
companies Morningstar does not rate."""
from __future__ import annotations

from backend.data import realsustainalytics as rs
from backend.tests.conftest import RaterRow


def test_scored_by_year_carries_values_on_the_assessment_year():
    scored = rs.scored_by_year()
    # A covered company has a numeric Sustainalytics risk on year 2026.
    assert "U96" in scored
    (year, entry), = scored["U96"].items()
    assert year == 2026 and entry["sustainalytics"] == 28.6
    # Companies Morningstar does not rate are absent — never fabricated.
    assert "GULF" not in scored and "POW" not in scored


def test_overlay_writes_the_value_and_creates_the_year_row():
    # Only a 2023 seed row exists; the overlay must add the 2026 real observation.
    raters = [RaterRow("U96", 2023, "AAA", 44.0, None)]
    out = rs.overlay(raters)
    row_2026 = [r for r in out if r.company_id == "U96" and r.year == 2026]
    assert row_2026 and row_2026[0].sustainalytics_risk == 28.6
    # the original seed row is left untouched
    assert any(r.year == 2023 and r.sustainalytics_risk == 44.0 for r in out)
