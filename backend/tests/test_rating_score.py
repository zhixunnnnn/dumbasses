"""The ESG RATING score (rating_score.py): agency consensus on a 0..100 quality scale,
SASB-material-weighted, with CDP confined to the Environmental pillar and N.A. (never 0)
when no agency rates the company. S&P is dropped and must never contribute."""
from __future__ import annotations

from backend.engine import config
from backend.engine.models import RaterPercentiles
from backend.engine.normalize import normalize_raters
from backend.engine.rating_score import (
    AGENCY_PILLARS,
    agency_quality,
    rating_from_pcts,
    rating_score,
)
from backend.tests.conftest import RaterRow, make_company, make_dataset

YEAR = config.END_YEAR


def _bank_dataset():
    companies = [make_company(c) for c in ["STRONG", "WEAK", "F1", "F2", "F3", "F4"]]
    raw = {
        "STRONG": ("AAA", 5.0, 92.0),
        "WEAK":   ("B",   45.0, 38.0),
        "F1":     ("A",   20.0, 70.0),
        "F2":     ("AA",  15.0, 78.0),
        "F3":     ("BBB", 28.0, 60.0),
        "F4":     ("BB",  33.0, 52.0),
    }
    raters = [RaterRow(c, YEAR, m, s, sp) for c, (m, s, sp) in raw.items()]
    return make_dataset(companies=companies, raters=raters)


def test_agency_quality_maps_each_scale_to_0_100_higher_better():
    row = RaterRow("X", YEAR, "AA", 30.0, 88.0, cdp_letter="A")
    assert agency_quality("msci", row) == 85.7          # AA on the 7-point scale
    assert agency_quality("cdp", row) == 100.0          # A is top of CDP
    assert agency_quality("sustainalytics", row) == 70.0  # 100 - risk 30
    # S&P is dropped and must never yield a quality even if a value is present.
    assert "sp" not in AGENCY_PILLARS


def test_cdp_informs_environmental_pillar_only():
    assert AGENCY_PILLARS["cdp"] == ("E",)
    ds = make_dataset(companies=[make_company("C")],
                      raters=[RaterRow("C", YEAR, "AAA", None, None, cdp_letter="B")])
    # a percentile view with MSCI (all pillars) + CDP (E only) both present
    pcts = RaterPercentiles(company_id="C", msci_pct=90.0, cdp_pct=60.0,
                            real_raters=["msci", "cdp"], rater_years={"msci": YEAR, "cdp": YEAR})
    rs = rating_from_pcts(ds, "C", YEAR, pcts)
    # MSCI AAA -> 100 feeds all pillars; CDP B -> 75 additionally feeds E, pulling E below S/G.
    assert rs.pillars["E"] < rs.pillars["S"] == rs.pillars["G"] == 100.0
    assert rs.pillars["E"] == 87.5


def _real_pcts(cid: str) -> RaterPercentiles:
    """Percentiles with MSCI + Sustainalytics marked REAL (the rating only uses real channels)."""
    return RaterPercentiles(company_id=cid, msci_pct=50.0, sustainalytics_pct=50.0,
                            real_raters=["msci", "sustainalytics"],
                            rater_years={"msci": YEAR, "sustainalytics": YEAR})


def test_rating_ranks_strong_above_weak_and_stays_in_range():
    ds = _bank_dataset()
    strong = rating_from_pcts(ds, "STRONG", YEAR, _real_pcts("STRONG"))
    weak = rating_from_pcts(ds, "WEAK", YEAR, _real_pcts("WEAK"))
    assert strong.total is not None and weak.total is not None
    assert 0.0 <= weak.total < strong.total <= 100.0
    assert strong.agencies and "sp" not in strong.agencies   # S&P never contributes


def test_illustrative_agency_values_are_never_used():
    # a company whose MSCI/Sustainalytics are present but NOT real -> no agency input at all.
    ds = _bank_dataset()
    seeded = RaterPercentiles(company_id="STRONG", msci_pct=90.0, sustainalytics_pct=90.0,
                              real_raters=[], rater_years={"msci": YEAR, "sustainalytics": YEAR})
    rs = rating_from_pcts(ds, "STRONG", YEAR, seeded)
    assert rs.agencies == []          # illustrative values dropped
    assert rs.total is config.NA      # nothing real -> N.A., never a seeded score


def test_no_agency_coverage_is_na_never_zero():
    ds = make_dataset(companies=[make_company("EMPTY")], raters=[])
    rs = rating_score(ds, "EMPTY", YEAR)
    assert rs.total is config.NA          # None, not a fabricated 0
    assert rs.pillars == {"E": None, "S": None, "G": None}
    assert rs.agencies == []


def test_a_scored_rating_is_always_real():
    # the score uses only real agencies + CDP + Climate TRACE, so a produced rating is "real",
    # never mixed/illustrative.
    ds = _bank_dataset()
    rs = rating_from_pcts(ds, "STRONG", YEAR, _real_pcts("STRONG"))
    assert rs.total is not None and rs.provenance == "real"
