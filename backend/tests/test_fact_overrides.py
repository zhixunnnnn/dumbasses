from __future__ import annotations

import pytest

from backend.app.fact_overrides import FactOverrideStore, OverrideCreate


@pytest.fixture()
def store(tmp_path) -> FactOverrideStore:
    return FactOverrideStore(tmp_path / "overrides.sqlite3")


def test_override_replaces_the_engine_value_and_records_what_it_replaced(store):
    store.upsert(
        OverrideCreate(
            companyId="9CI",
            field="evidence_score",
            value=71.2,
            note="Restated in the FY2023 report",
        )
    )
    payload = store.apply({"evidence_score": 64.75}, "9CI")

    assert payload["evidence_score"] == 71.2
    applied = payload["overrides"][0]
    assert applied["engine_value"] == 64.75
    assert applied["note"] == "Restated in the FY2023 report"
    # The agent needs to be told the value is authoritative, not just given it.
    assert "overrides_note" in payload


def test_nested_fields_are_patched_in_place(store):
    store.upsert(OverrideCreate(companyId="9CI", field="pillars.S", value=44.0))
    payload = store.apply({"pillars": {"E": 78.0, "S": 25.0, "G": 25.0}}, "9CI")

    assert payload["pillars"] == {"E": 78.0, "S": 44.0, "G": 25.0}


def test_repinning_a_field_replaces_it_rather_than_stacking(store):
    store.upsert(OverrideCreate(companyId="9CI", field="evidence_score", value=71.2))
    store.upsert(OverrideCreate(companyId="9CI", field="evidence_score", value=73.0))

    rows = store.list(company_id="9CI")
    assert len(rows) == 1
    assert rows[0].value == 73.0


def test_expired_overrides_are_not_applied(store):
    store.upsert(
        OverrideCreate(
            companyId="BN4", field="confidence", value=0.9, expiresAt="2020-01-01"
        )
    )
    payload = store.apply({"confidence": 0.4}, "BN4")

    assert payload["confidence"] == 0.4
    assert "overrides" not in payload
    # It is retained for the audit trail, just inactive.
    assert store.list(company_id="BN4")[0].is_expired is True


def test_a_company_without_overrides_is_untouched(store):
    store.upsert(OverrideCreate(companyId="9CI", field="evidence_score", value=71.2))
    payload = store.apply({"evidence_score": 50.0}, "BN4")

    assert payload == {"evidence_score": 50.0}


@pytest.mark.parametrize(
    "field, value",
    [
        ("evidence_score", 150),          # above the field's max
        ("confidence", 55),               # percentage where a 0-1 ratio belongs
        ("pillars.X", 10),                # not a real pillar
        ("company.id", "spoofed"),        # not on the whitelist at all
        ("report_source", "   "),         # empty after trimming
    ],
)
def test_invalid_values_are_rejected(store, field, value):
    with pytest.raises(ValueError):
        store.upsert(OverrideCreate(companyId="9CI", field=field, value=value))


def test_bare_date_expiry_covers_the_whole_final_day(store):
    record = store.upsert(
        OverrideCreate(
            companyId="9CI", field="evidence_score", value=71.2, expiresAt="2099-12-31"
        )
    )
    assert record.expires_at == "2099-12-31T23:59:59+00:00"
    assert record.is_expired is False
