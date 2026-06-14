"""T2 (flip) and T6 (rank-based normalization)."""
from __future__ import annotations

from backend.engine import config
from backend.engine.divergence import divergence_index
from backend.engine.normalize import normalize_raters
from backend.tests.conftest import RaterRow, make_company, make_dataset

YEAR = config.END_YEAR


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


def test_divergence_needs_two_raters():
    companies = [make_company("ONLY")] + [make_company(f"P{i}") for i in range(5)]
    raters = [RaterRow("ONLY", YEAR, "A", None, None)] + [
        RaterRow(f"P{i}", YEAR, "BBB", 20.0, 60.0) for i in range(5)
    ]
    ds = make_dataset(companies=companies, raters=raters)
    pcts = normalize_raters(ds, YEAR)
    assert divergence_index(pcts["ONLY"]) is None  # 1 rater -> N.A., never fabricated
    assert divergence_index(pcts["P0"]) is not None
