"""T2 (flip), T6 (rank-based normalization) and the realness gate on consensus/divergence."""
from __future__ import annotations

import pytest

from backend.engine import config, normalize
from backend.engine.divergence import divergence_index
from backend.engine.normalize import consensus, normalize_raters
from backend.tests.conftest import RaterRow, make_company, make_dataset

YEAR = config.END_YEAR


@pytest.fixture
def strict_mode(monkeypatch):
    """Turn the illustrative fallback OFF — the real-only mode config keeps reachable."""
    monkeypatch.setattr(config, "ALLOW_ILLUSTRATIVE_FALLBACK", False)


@pytest.fixture
def fallback_mode(monkeypatch):
    """Turn the illustrative fallback ON (the prototype default)."""
    monkeypatch.setattr(config, "ALLOW_ILLUSTRATIVE_FALLBACK", True)


@pytest.fixture
def real_channels(monkeypatch):
    """Declare which rater channels count as REAL, without touching the on-disk caches."""
    def _set(*keys, companies=None):
        monkeypatch.setattr(normalize, "real_raters_cache", lambda: {})
        monkeypatch.setattr(
            normalize, "manual_raters_cache",
            lambda: {cid: {YEAR: list(keys)}
                     for cid in (companies or ["STRONG", "WEAK", "F1", "F2", "F3", "F4"])})
    return _set


def _bank_dataset(sp_scale: float = 1.0):
    """Six banks; STRONG clearly best, WEAK clearly worst, on all three raters."""
    companies = [make_company(c) for c in ["STRONG", "WEAK", "F1", "F2", "F3", "F4"]]
    # (msci_letter, sustainalytics_risk LOWER=better, sp_global higher=better)
    raw = {
        "STRONG": ("AAA", 5.0, 92.0),
        "WEAK":   ("B",   45.0, 38.0),
        "F1":     ("A",   20.0, 70.0),
        "F2":     ("AA",  15.0, 78.0),
        "F3":     ("BBB", 28.0, 60.0),
        "F4":     ("BB",  33.0, 52.0),
    }
    raters = [RaterRow(c, YEAR, m, s, sp * sp_scale) for c, (m, s, sp) in raw.items()]
    return make_dataset(companies=companies, raters=raters)


def test_T2_flip_all_raters_rank_strong_above_weak():
    pcts = normalize_raters(_bank_dataset(), YEAR)
    strong, weak = pcts["STRONG"], pcts["WEAK"]
    # all three must point the same way after inverting Sustainalytics
    assert strong.msci_pct > weak.msci_pct, "MSCI inverted"
    assert strong.sp_pct > weak.sp_pct, "S&P inverted"
    assert strong.sustainalytics_pct > weak.sustainalytics_pct, "Sustainalytics flip missing!"
    # higher=better everywhere: strong near the top, weak near the bottom
    assert strong.sustainalytics_pct > 80 and weak.sustainalytics_pct < 20


def test_T6_rank_based_invariant_to_scale():
    base = normalize_raters(_bank_dataset(sp_scale=1.0), YEAR)
    scaled = normalize_raters(_bank_dataset(sp_scale=0.5), YEAR)  # 0..100 -> 0..50, order preserved
    for cid in base:
        assert base[cid].sp_pct == scaled[cid].sp_pct, f"{cid} percentile moved on a pure rescale"


@pytest.mark.parametrize("fallback", [True, False])
def test_divergence_needs_two_raters(real_channels, monkeypatch, fallback):
    """MIN_RATERS_FOR_DIVERGENCE is a data absence, not a policy: one rater yields no
    spread in EITHER mode."""
    monkeypatch.setattr(config, "ALLOW_ILLUSTRATIVE_FALLBACK", fallback)
    real_channels("msci", "sustainalytics", "sp",
                  companies=[f"P{i}" for i in range(5)] + ["ONLY"])
    companies = [make_company("ONLY")] + [make_company(f"P{i}") for i in range(5)]
    raters = [RaterRow("ONLY", YEAR, "A", None, None)] + [
        RaterRow(f"P{i}", YEAR, "BBB", 20.0, 60.0) for i in range(5)
    ]
    ds = make_dataset(companies=companies, raters=raters)
    pcts = normalize_raters(ds, YEAR)
    assert divergence_index(pcts["ONLY"]) is None  # 1 rater -> N.A., never fabricated
    assert divergence_index(pcts["P0"]) is not None


def test_strict_mode_is_na_with_one_real_rater(real_channels, strict_mode):
    """Strict mode (ALLOW_ILLUSTRATIVE_FALLBACK=False) still refuses to splice a real MSCI
    onto seeded S&P/Sustainalytics — that blend is what made Keppel's 87.8 misleading."""
    real_channels("msci")
    strong = normalize_raters(_bank_dataset(), YEAR)["STRONG"]
    assert strong.real_raters == ["msci"]
    assert len(strong.real_available()) == 1
    assert divergence_index(strong) is None
    assert consensus(strong) is None


def test_fallback_mode_computes_but_labels_the_blend(real_channels, fallback_mode):
    """With the fallback on the same figures compute from every channel — and are labelled
    "mixed", never "real", because seeded percentiles contributed."""
    real_channels("msci")
    strong = normalize_raters(_bank_dataset(), YEAR)["STRONG"]
    assert set(strong.contributing()) == {"msci", "sp", "sustainalytics"}
    assert consensus(strong) is not None and divergence_index(strong) is not None
    assert strong.provenance() == "mixed"


def test_fallback_with_no_real_rater_is_labelled_illustrative(real_channels, fallback_mode):
    real_channels(companies=["STRONG"])          # no channel declared real
    strong = normalize_raters(_bank_dataset(), YEAR)["STRONG"]
    assert consensus(strong) is not None
    assert strong.provenance() == "illustrative"


def test_a_blended_figure_is_never_labelled_real(real_channels, fallback_mode):
    """The invariant the whole exercise exists to protect."""
    for keys in (("msci",), ("msci", "sp"), ("msci", "sp", "sustainalytics")):
        real_channels(*keys)
        p = normalize_raters(_bank_dataset(), YEAR)["STRONG"]
        seeded = [k for k in p.contributing() if k not in p.real_raters]
        if seeded:
            assert p.provenance() != "real", f"{keys} + seeded {seeded} labelled real"
        else:
            assert p.provenance() == "real"


def test_divergence_and_consensus_computed_once_two_raters_are_real(real_channels, strict_mode):
    """The gate is satisfiable, not a permanent off switch: hand-enter a second real
    rating and both numbers come back — over the REAL channels only."""
    real_channels("msci", "sp", companies=["SPLIT"])
    ds = _bank_dataset()
    # SPLIT is top-of-scale on MSCI and bottom on S&P — a genuine disagreement
    ds.raters.append(RaterRow("SPLIT", YEAR, "AAA", 44.0, 39.0))
    ds.companies["SPLIT"] = make_company("SPLIT")
    split = normalize_raters(ds, YEAR)["SPLIT"]
    real = split.real_available()
    assert real == [split.msci_pct, split.sp_pct]     # seeded Sustainalytics excluded
    assert divergence_index(split) == round(max(real) - min(real), 2) > 0
    assert consensus(split) == round(sum(real) / len(real), 2)


def test_percentile_is_na_below_the_peer_floor(real_channels, fallback_mode):
    """A rank over fewer than MIN_PEERS_FOR_SECTOR_RANK names in TOTAL is noise."""
    real_channels("msci", "sust", "sp", companies=["A1", "A2"])
    n = config.MIN_PEERS_FOR_SECTOR_RANK - 3
    assert n >= 1
    companies = [make_company(f"A{i}") for i in range(1, n + 1)]
    raters = [RaterRow(f"A{i}", YEAR, "A", 20.0, 60.0) for i in range(1, n + 1)]
    pcts = normalize_raters(make_dataset(companies=companies, raters=raters), YEAR)
    only = pcts["A1"]
    assert only.msci_pct is None and only.sp_pct is None and only.sustainalytics_pct is None
    assert divergence_index(only) is None and consensus(only) is None


def test_year_with_no_rater_row_is_na_not_carried_forward():
    """Moving END_YEAR past the raters' coverage must yield N.A., never the last
    year's value dressed up as this year's."""
    ds = _bank_dataset()                      # raters exist only for YEAR
    pcts = normalize_raters(ds, YEAR + 1)
    p = pcts["STRONG"]
    assert (p.msci_pct, p.sp_pct, p.sustainalytics_pct) == (None, None, None)
    assert consensus(p) is None
    assert divergence_index(p) is None


# --- a real observation OUTSIDE the analysis year is used, and keeps its own year -----
def test_latest_real_rating_is_ranked_without_being_re_dated(monkeypatch, fallback_mode):
    """A rating measured after END_YEAR must still count, on ITS OWN year.

    Re-dating it onto END_YEAR would falsify the observation; ignoring it would hide real
    data. So the value is ranked inside its own year's cohort and `rater_years` carries the
    year it was actually measured in.
    """
    later = YEAR + 1
    companies = [make_company(c) for c in ["STRONG", "WEAK", "F1", "F2", "F3", "F4"]]
    raters = [r for r in _bank_dataset().raters]
    # a whole cohort of CDP readings that exist only in `later` — exactly the shape of the
    # 2025 CDP scores table under a 2024 window
    cdp = {"STRONG": "A", "WEAK": "D", "F1": "B", "F2": "A-", "F3": "C", "F4": "C-"}
    for cid, letter in cdp.items():
        raters.append(RaterRow(cid, later, None, None, None, letter))
    ds = make_dataset(companies=companies, raters=raters)

    monkeypatch.setattr(normalize, "real_raters_cache", lambda: {})
    monkeypatch.setattr(normalize, "manual_raters_cache", lambda: {})
    monkeypatch.setattr(normalize, "report_raters_cache",
                        lambda: {cid: {later: ["cdp"]} for cid in cdp})

    pcts = normalize_raters(ds, YEAR)
    strong, weak = pcts["STRONG"], pcts["WEAK"]

    # the later reading is ranked ...
    assert strong.cdp_pct is not None and weak.cdp_pct is not None
    assert strong.cdp_pct > weak.cdp_pct
    # ... it is REAL, so the figure stops being purely illustrative ...
    assert "cdp" in strong.real_raters
    assert strong.provenance() == "mixed"
    # ... and it is NOT re-dated: the year travels with the value.
    assert strong.rater_years["cdp"] == later
    assert strong.rater_years["msci"] == YEAR     # the seeded channels stay in their year
    # nothing was written back into the analysis year's row
    end_row = next(r for r in ds.raters if r.company_id == "STRONG" and r.year == YEAR)
    assert end_row.cdp_letter is None


def test_a_real_year_is_skipped_when_its_cohort_is_too_thin(monkeypatch, fallback_mode):
    """One lone observation in a later year cannot be ranked, so the analysis year's value
    is used instead — the fallback never invents a percentile out of a cohort of one."""
    later = YEAR + 1
    ds = _bank_dataset()
    raters = list(ds.raters) + [RaterRow("STRONG", later, "AAA", None, None)]
    ds = make_dataset(companies=list(ds.companies.values()), raters=raters)
    monkeypatch.setattr(normalize, "real_raters_cache", lambda: {})
    monkeypatch.setattr(normalize, "manual_raters_cache", lambda: {})
    monkeypatch.setattr(normalize, "report_raters_cache", lambda: {"STRONG": {later: ["msci"]}})

    p = normalize_raters(ds, YEAR)["STRONG"]
    assert p.rater_years["msci"] == YEAR
    assert "msci" not in p.real_raters      # the YEAR reading is seeded, and says so
