"""The ESRS double-materiality composite: finance-tilted blend of the ESG rating (financial)
and peer-ranked carbon intensity (impact), minus a materiality-gap greenwashing penalty."""
from __future__ import annotations

from backend.engine import config, double_materiality as dm


def test_carbon_intensity_uses_market_cap_and_fx_and_guards_glitches():
    # 1,000,000 tCO2e over a 10B MYR cap (~2.2B USD) -> ~455 tCO2e/$M
    v = dm.carbon_intensity(1_000_000, 10_000_000_000, "MYR")
    assert v is not None and 400 < v < 500
    assert dm.carbon_intensity(1_000_000, None, "MYR") is None      # no cap -> N.A.
    assert dm.carbon_intensity(1_000_000, 10, "MYR") is None        # absurd -> guarded to N.A.


def test_impact_scores_rank_cleaner_higher():
    scores = dm.impact_scores({"A": 100.0, "B": 500.0, "C": 2000.0, "D": None})
    assert scores["A"] == 100.0 and scores["C"] == 0.0             # cleanest -> 100, dirtiest -> 0
    assert 0 < scores["B"] < 100
    assert scores["D"] is None                                     # no intensity -> N.A.


def test_greenwashing_is_the_materiality_gap():
    penalty, drivers = dm.greenwashing_penalty(financial=80.0, impact=40.0, controversies=0)
    assert penalty == round(config.GREENWASH_GAP_K * 40, 1) and drivers
    # rated no better than it runs -> no penalty
    assert dm.greenwashing_penalty(50.0, 70.0)[0] == 0.0


def test_composite_is_finance_tilted_and_degrades_honestly():
    comp, note = dm.composite(80.0, 40.0, penalty=0.0)
    assert comp == round(config.DM_WEIGHT_FINANCIAL * 80 + config.DM_WEIGHT_IMPACT * 40, 1)
    assert note is None
    # impact N.A. -> composite is the financial half (minus penalty), and says so
    comp2, note2 = dm.composite(70.0, None, penalty=5.0)
    assert comp2 == 65.0 and note2 and "financial half only" in note2
    # financial N.A. -> composite N.A. (never fabricated)
    assert dm.composite(None, 50.0, 0.0)[0] is None
