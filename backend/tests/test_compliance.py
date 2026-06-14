"""T9 — compliance never penalises a not-yet-in-force regulation or an unknown status."""
from __future__ import annotations

from backend.engine import config
from backend.engine.regulations import compliance_gap
from backend.tests.conftest import (
    DocumentRow, RegComplianceRow, RegulationRow, make_company, make_dataset,
)

YEAR = config.END_YEAR


def _ds():
    comp = make_company("BANK", sector="Financials", industry="Commercial Banks")
    regs = [
        RegulationRow("R_MET", "SG", "Existing reg", "SGX-listed", "disclose", 2017),
        RegulationRow("R_MISS", "SG", "In-force reg", "SGX-listed", "disclose", 2020),
        RegulationRow("R_FUTURE", "SG", "Future reg (ISSB-like)", "SGX-listed", "disclose", 2025),
        RegulationRow("R_UNKNOWN", "SG", "Unknown-status reg", "SGX-listed", "disclose", 2020),
    ]
    comp_rows = [
        RegComplianceRow("BANK", "R_MET", YEAR, "MET", "BANK-SR"),
        RegComplianceRow("BANK", "R_MISS", YEAR, "MISSING", None),
        # R_FUTURE: not in force in 2023; R_UNKNOWN: no row at all
    ]
    doc = DocumentRow("BANK", "BANK-SR", "SR", YEAR, None, 1,
                      "In FY2023 the bank disclosed its climate approach.")
    return make_dataset(companies=[comp], regulations=regs, reg_compliance=comp_rows, documents=[doc])


def test_T9_future_reg_is_na_not_violation():
    cg = compliance_gap(_ds(), "BANK", YEAR)
    assert [r.reg_id for r in cg.not_in_force] == ["R_FUTURE"]
    assert "R_FUTURE" not in [r.reg_id for r in cg.missing]


def test_T9_unknown_status_excluded_from_denominator():
    cg = compliance_gap(_ds(), "BANK", YEAR)
    ids = {r.reg_id for r in (cg.met + cg.partial + cg.missing)}
    assert "R_UNKNOWN" not in ids                     # unknown never counted
    # denominator = MET + MISSING = 2, one missing -> 0.5 (R_FUTURE & R_UNKNOWN excluded)
    assert cg.score == 0.5
