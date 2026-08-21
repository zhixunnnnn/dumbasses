"""Industry benchmarks: computed panel median, hand-entered override, and validation."""
from __future__ import annotations

import pytest

from backend.engine import config
from backend.engine.benchmarks import (
    computed_benchmarks,
    delete_benchmark,
    get_benchmarks,
    set_benchmark,
)
from backend.tests.conftest import DocumentRow, make_company, make_dataset

INDUSTRY = "Commercial Banks"          # a real key in sasb_materiality.json
DOC_TEXT = ("The bank expanded green financing and climate risk disclosure in 2023. "
            "It also strengthened data security and board oversight.")


@pytest.fixture
def _isolated_db(monkeypatch, tmp_path):
    """Overrides are persisted, so every test gets its own SQLite file."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "benchmarks.sqlite3")
    yield


def _panel(n: int = config.MIN_PEERS_FOR_SECTOR_RANK):
    """A panel big enough to support a median (the floor is MIN_PEERS_FOR_SECTOR_RANK)."""
    companies, docs = [], []
    for cid in [f"C{i}" for i in range(n)]:
        companies.append(make_company(cid, sector="Banks", industry=INDUSTRY))
        docs.append(DocumentRow(cid, f"{cid}-SR{config.END_YEAR}", f"{cid} SR",
                                config.END_YEAR, None, 1, DOC_TEXT))
    return make_dataset(companies=companies, documents=docs)


def _row(rows, industry, metric):
    return next(r for r in rows if r["industry"] == industry and r["metric"] == metric)


def test_computed_median_is_none_without_evidence(_isolated_db):
    """A company with no documents scores N.A., so it must not drag the median to 0."""
    ds = make_dataset(companies=[make_company("EMPTY", industry=INDUSTRY)])
    assert computed_benchmarks(ds)[INDUSTRY]["total"] is None


def test_thin_median_is_labelled_with_its_peer_count(_isolated_db):
    """A median over three names is shown, but the SOURCE says how thin it is — the label
    is what stops it reading as an authoritative industry bar."""
    n = config.MIN_PEERS_FOR_SECTOR_RANK - 2
    row = _row(get_benchmarks(_panel(n)), INDUSTRY, "total")
    assert row["value"] is not None
    assert row["peers"] == n
    assert f"n={n}" in row["source"] and "below peer floor" in row["source"]
    assert row["is_override"] is False


def test_strict_mode_restores_na_for_a_thin_median(_isolated_db, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_ILLUSTRATIVE_FALLBACK", False)
    ds = _panel(config.MIN_PEERS_FOR_SECTOR_RANK - 1)
    assert computed_benchmarks(ds)[INDUSTRY]["total"] is None
    row = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert row["value"] is None and row["source"] is None


def test_an_industry_with_no_scored_company_is_always_na(_isolated_db):
    """An absence, not a policy choice — N.A. in both modes, never 0."""
    ds = make_dataset(companies=[make_company("EMPTY", industry=INDUSTRY)])
    row = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert row["value"] is None and row["source"] is None and row["peers"] == 0


def test_override_is_shown_even_when_the_panel_is_too_thin(_isolated_db):
    """A CGSI override always wins and is always shown, floor or no floor."""
    ds = _panel(config.MIN_PEERS_FOR_SECTOR_RANK - 1)
    set_benchmark(INDUSTRY, "total", 58.0, "CGSI")
    row = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert row["value"] == 58.0 and row["is_override"] is True and row["source"] == "CGSI"


def test_get_benchmarks_reports_panel_median(_isolated_db):
    ds = _panel()
    expected = computed_benchmarks(ds)[INDUSTRY]["total"]
    row = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert expected is not None
    assert row["value"] == expected
    assert row["is_override"] is False
    assert row["source"].startswith("panel median") and "below peer floor" not in row["source"]


def test_stored_override_beats_computed_median(_isolated_db):
    ds = _panel()
    set_benchmark(INDUSTRY, "total", 61.5, "CGSI")

    row = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert row["value"] == 61.5
    assert row["is_override"] is True and row["source"] == "CGSI"
    assert row["updated_at"]
    # only the overridden metric is replaced; the pillars stay computed
    assert _row(get_benchmarks(ds), INDUSTRY, "E")["is_override"] is False

    delete_benchmark(INDUSTRY, "total")
    reverted = _row(get_benchmarks(ds), INDUSTRY, "total")
    assert reverted["is_override"] is False
    assert reverted["value"] == computed_benchmarks(ds)[INDUSTRY]["total"]


def test_delete_unknown_override_raises(_isolated_db):
    with pytest.raises(KeyError):
        delete_benchmark(INDUSTRY, "E")


@pytest.mark.parametrize("industry, metric, value, source", [
    ("Default", "total", 50.0, "CGSI"),          # the generic rubric is not an industry
    ("Space Tourism", "total", 50.0, "CGSI"),    # unknown industry
    (INDUSTRY, "X", 50.0, "CGSI"),               # unknown metric
    (INDUSTRY, "total", 101.0, "CGSI"),          # out of the 0..100 score range
    (INDUSTRY, "total", -1.0, "CGSI"),
    (INDUSTRY, "total", 50.0, "   "),            # a benchmark without provenance
])
def test_set_benchmark_validation(_isolated_db, industry, metric, value, source):
    with pytest.raises(ValueError):
        set_benchmark(industry, metric, value, source)
