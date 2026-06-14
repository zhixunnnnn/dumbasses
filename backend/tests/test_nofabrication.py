"""T7 — missing data is None/N.A., never a fabricated default; no default-fills in the pipeline."""
from __future__ import annotations

from pathlib import Path

from backend.engine import config
from backend.engine.normalize import normalize_raters
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
