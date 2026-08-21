"""T7 — missing data is None/N.A., never a fabricated default; no default-fills in the pipeline."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.engine import config
from backend.engine.normalize import normalize_raters
from backend.engine.score import evidence_score
from backend.tests.conftest import RaterRow, make_company, make_dataset

YEAR = config.END_YEAR


def test_T7_missing_rater_is_none_not_zero():
    companies = [make_company("GAP")] + [make_company(f"P{i}") for i in range(5)]
    raters = [RaterRow("GAP", YEAR, None, None, None)] + [
        RaterRow(f"P{i}", YEAR, "A", 20.0, 60.0) for i in range(5)
    ]
    pcts = normalize_raters(make_dataset(companies=companies, raters=raters), YEAR)
    gap = pcts["GAP"]
    assert gap.msci_pct is None and gap.sp_pct is None and gap.sustainalytics_pct is None
    assert gap.available() == []  # nothing invented


def test_T7_no_default_fill_of_rater_data_in_pipeline():
    """Static scan: engine must not pandas-fillna or coalesce missing rater/score data."""
    engine_dir = config.ENGINE_DIR
    offenders = []
    for py in engine_dir.glob("*.py"):
        src = py.read_text("utf-8")
        if ".fillna(" in src or ".interpolate(" in src:
            offenders.append(py.name)
    assert not offenders, f"default-fill found in: {offenders}"


def test_T7_import_uses_null_for_missing():
    """The Excel importer converts NaN -> None (NULL), the OPPOSITE of fabrication."""
    src = (config.DATA_DIR / "import_excel.py").read_text("utf-8")
    assert "where(pd.notnull(df), None)" in src


def test_T7_company_without_evidence_scores_na_not_zero():
    """No covered topic means nothing to divide — the evidence score is N.A. A 0 would
    read as 'audited and found empty' instead of 'we have no evidence'."""
    ds = make_dataset(companies=[make_company("NODOCS")])
    es = evidence_score(ds, "NODOCS", YEAR)
    assert es.total is None
    assert all(v is None for v in es.pillars.values())


def test_no_invented_reference_companies_remain():
    """The 48 generated ASEAN "peers" ("Commercial ASEAN 1", ...) did not exist. They were
    the population behind every rater percentile, evidence percentile and industry median,
    so nothing may be left of them — universe or dependent rows."""
    if not config.DB_PATH.exists():
        pytest.skip("no database on this checkout")
    conn = sqlite3.connect(str(config.DB_PATH))
    try:
        conn.row_factory = sqlite3.Row
        assert conn.execute(
            "SELECT COUNT(*) FROM universe WHERE scope='reference'").fetchone()[0] == 0
        known = {r[0] for r in conn.execute("SELECT company_id FROM universe")} | {config.STI_ID}
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if "company_id" not in cols:
                continue
            # NULL is "no company" (e.g. a universe-scope research run), not a dangling
            # reference to a deleted one.
            orphans = {r[0] for r in conn.execute(
                f"SELECT DISTINCT company_id FROM {table} "
                "WHERE company_id IS NOT NULL")} - known
            assert not orphans, f"{table} still references removed companies: {sorted(orphans)}"
    finally:
        conn.close()


def test_seed_no_longer_generates_a_reference_panel():
    """The generator itself is gone, so a rebuild cannot reintroduce the fake panel."""
    src = (config.DATA_DIR / "seed.py").read_text("utf-8")
    for marker in ("REF_SECTORS", "REF_COUNTRIES", "_insert_reference_rows", "ASEAN {n}"):
        assert marker not in src, f"seed.py still generates reference companies ({marker})"


# --- extending the SEEDED window vs carrying a REAL value forward -------------
def test_seeded_trajectories_cover_the_whole_analysis_window():
    """Moving END_YEAR must not leave the illustrative dataset short. The seed extends to
    cover config.YEARS so rater/compliance figures keep rendering (labelled illustrative)
    instead of collapsing to N.A. everywhere."""
    from backend.data.seed import DEMO, demo_series

    for company in DEMO:
        for series in demo_series(company):
            assert len(series) == len(config.YEARS), company["id"]


def test_extension_continues_the_authored_trend_not_a_copy():
    """A rising series keeps rising; a flat one stays flat. Repeating the last value would
    quietly turn every trend into a plateau."""
    from backend.data.seed import extend_letters, extend_numeric

    assert extend_numeric([70, 73, 76], 5, 0.0, 100.0) == [70.0, 73.0, 76.0, 79.0, 82.0]
    assert extend_numeric([44, 44, 44], 5, 0.0, 100.0) == [44.0] * 5
    assert extend_numeric([2, 1], 4, 0.0, 100.0) == [2.0, 1.0, 0.0, 0.0]     # clamped
    assert extend_letters(["A", "AA"], 4) == ["A", "AA", "AAA", "AAA"]        # ladder end
    assert extend_letters(["BB", "BB"], 4) == ["BB"] * 4                      # plateaued


def test_seeded_extension_is_never_labelled_real():
    """The extension is only honest because it is labelled. Seeded rows must not appear in
    any real-rater cache, so provenance() reports them illustrative."""
    from backend.engine import ingest, normalize

    ds = ingest.load()
    pcts = normalize.normalize_raters(ds, config.END_YEAR)
    for cid in ds.demo_ids():
        p = pcts[cid]
        seeded = [k for k in p.contributing() if k not in p.real_raters]
        if seeded:
            assert p.provenance() != "real", f"{cid}: seeded {seeded} labelled real"


def test_a_real_rating_is_never_moved_to_the_analysis_year():
    """The distinction the seed extension must not blur: a real observation keeps its own
    year. CDP's current table is a 2025 observation, so the overlay must NOT drop a CDP
    letter onto END_YEAR just because that is the year the dashboard renders."""
    from backend.data.realcdp import overlay, scored_by_year
    from backend.engine.ingest import RaterRow

    by_year = scored_by_year()
    if not by_year:
        pytest.skip("no CDP scores cached")
    off_window = {cid: years for cid, years in by_year.items()
                  if config.END_YEAR not in years}
    assert off_window, "expected at least one CDP score outside the analysis year"
    for cid, years in off_window.items():
        rows = [r for r in overlay([RaterRow(cid, config.END_YEAR, None, None, None)])
                if r.company_id == cid]
        at_end = next(r for r in rows if r.year == config.END_YEAR)
        assert at_end.cdp_letter is None, (
            f"{cid}: a {sorted(years)} CDP observation was re-dated to {config.END_YEAR}")
        for year in years:
            landed = next(r for r in rows if r.year == year)
            assert landed.cdp_letter == years[year]["cdp"]
