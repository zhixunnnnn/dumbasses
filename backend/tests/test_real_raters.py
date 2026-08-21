"""Hand-entered rater ratings (provenance required) and ratings extracted from the
companies' own sustainability reports. Both feed the REAL-rater gate on consensus and
divergence, so both have to refuse anything they cannot stand behind."""
from __future__ import annotations

import pytest

from backend.data.realratings import extract_ratings
from backend.engine import config
from backend.engine.ingest import RaterRow
from backend.engine.manual_raters import delete_manual_rater, get_manual_raters, overlay

YEAR = config.END_YEAR


# --------------------------------------------------------------------------- #
# report-disclosed ratings
# --------------------------------------------------------------------------- #
def _ratings(text, report_year=2024):
    return [(r["rater"], r["value_raw"], r["assessment_year"])
            for r in extract_ratings(text, report_year, "http://x/r.pdf", "SR")
            if r["kind"] == "rating"]


def test_extracts_the_rating_and_the_year_the_sentence_states():
    text = ("Our last CDP Climate Change score received in 2023 was a 'B' "
            "Received a rating of AA in the MSCI ESG Ratings assessment in 2024")
    assert ("cdp", "B", 2023) in _ratings(text)      # NOT the 2024 report year
    assert ("msci", "AA", 2024) in _ratings(text)


@pytest.mark.parametrize("text, why", [
    ("We are an MSCI ESG Leaders index constituent.", "membership, no value"),
    ("CDP recognised our disclosure leadership this year.", "rater named, no value"),
    ("Keppel retained the highest triple-A rating in the MSCI ESG ratings.",
     "'triple-A' is not a rating of A"),
    ("Achieved in the CDP Water Security disclosure in the first attempt 'B' score.",
     "CDP water security is a different score from the climate one"),
])
def test_refuses_anything_that_is_not_a_stated_rating(text, why):
    assert _ratings(text) == [], why


def test_a_streak_year_is_not_the_assessment_year():
    """"retained AAA since 2020" in the 2024 report is a 2024 rating, not a 2020 one."""
    assert _ratings("Retained highest MSCI ESG rating of AAA since 2020.") == [
        ("msci", "AAA", 2024)]


def test_every_recorded_sentence_is_verbatim():
    text = ("ESG Indices and Ratings AA rating for MSCI ESG Ratings Assessment "
            "FTSE4Good constituent in the FTSE4Good Developed Index")
    rows = extract_ratings(text, 2024, "http://x/r.pdf", "SR")
    assert rows
    for row in rows:
        assert row["source_sentence"] in text


# --------------------------------------------------------------------------- #
# hand-entered ratings
# --------------------------------------------------------------------------- #
@pytest.fixture
def _isolated_db(monkeypatch, tmp_path):
    """Hand-entered rows are persisted, so every test gets its own SQLite file."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "raters.sqlite3")
    from backend.engine.db import bootstrap

    conn = bootstrap()
    conn.execute("INSERT INTO universe (company_id, ticker, name, scope) VALUES (?,?,?,?)",
                 ("D05", "D05.SI", "DBS Group", "demo"))
    conn.commit()
    conn.close()
    yield


def _set(rater="sp", value="65", observed="2026-08-01",
         url="https://www.spglobal.com/esg/scores/results?cid=1", note=None):
    from backend.engine.manual_raters import set_manual_rater

    return set_manual_rater("D05", rater, value, observed, url, note)


def test_hand_entered_rating_is_stored_with_its_provenance(_isolated_db):
    rows = _set()
    assert len(rows) == 1
    row = rows[0]
    assert row["rater"] == "sp" and row["value_raw"] == "65"
    assert row["observed_on"] == "2026-08-01" and row["source_url"].startswith("https://")


@pytest.mark.parametrize("kwargs, why", [
    ({"rater": "msci", "value": "ZZ"}, "off the MSCI letter scale"),
    ({"rater": "cdp", "value": "E"}, "off the CDP letter scale"),
    ({"rater": "sustainalytics", "value": "-4"}, "negative risk score"),
    ({"rater": "sp", "value": "140"}, "above the 0-100 S&P scale"),
    ({"rater": "sp", "value": ""}, "no value at all"),
    ({"observed": ""}, "no observation date"),
    ({"observed": "01/08/2026"}, "not an ISO date"),
    ({"observed": "2099-01-01"}, "observed in the future"),
    ({"url": ""}, "no source — a hand-entered rating without provenance is not real"),
    ({"url": "spglobal.com"}, "not a URL"),
    ({"rater": "moodys"}, "unknown rater"),
])
def test_rejects_off_scale_values_and_missing_provenance(_isolated_db, kwargs, why):
    with pytest.raises(ValueError):
        _set(**kwargs)
    assert get_manual_raters() == [], why


def test_unknown_company_is_rejected(_isolated_db):
    from backend.engine.manual_raters import set_manual_rater

    with pytest.raises(ValueError):
        set_manual_rater("NOPE", "sp", "65", "2026-08-01", "https://example.com/x")


def test_overlay_lands_on_the_latest_year_only(_isolated_db):
    """One current observation is one observation — never backfilled into a history."""
    _set(rater="msci", value="AA")
    rows = [RaterRow("D05", y, "BBB", 30.0, 50.0) for y in (YEAR - 1, YEAR)]
    latest, earlier = {r.year: r for r in overlay(rows)}[YEAR], \
        {r.year: r for r in overlay(rows)}[YEAR - 1]
    assert latest.msci_letter == "AA"
    assert earlier.msci_letter == "BBB"      # prior year untouched


def test_delete_reverts_to_the_underlying_value(_isolated_db):
    _set(rater="msci", value="AA")
    assert delete_manual_rater("D05", "msci") == []
    rows = overlay([RaterRow("D05", YEAR, "BBB", 30.0, 50.0)])
    assert rows[0].msci_letter == "BBB"
    with pytest.raises(KeyError):
        delete_manual_rater("D05", "msci")


# --------------------------------------------------------------------------- #
# CDP public scores table
# --------------------------------------------------------------------------- #
def test_cdp_icon_filenames_map_to_the_letter_scale():
    from backend.data.realcdp import parse_cell

    assert parse_cell("https://cdn.cdp.net/x/Climate-B-minus-Icon-grey-text.svg") == ("B-", None)
    assert parse_cell("https://cdn.cdp.net/x/Climate-A-Icon-grey-text.svg") == ("A", None)
    # CDP writes the modifier both ways across themes
    assert parse_cell("https://cdn.cdp.net/x/Water-A-Minus-Icon-grey-text.svg") == ("A-", None)


@pytest.mark.parametrize("cell, status", [
    ("Did not disclose", "did_not_disclose"),
    ("Not Scored", "not_scored"),
    ("See disclosing organisation", "see_parent"),
    ("", "absent"),
])
def test_cdp_non_scores_are_statuses_never_grades(cell, status):
    """"Did not disclose" means the company chose not to respond. It is a disclosure fact,
    not a bad grade, and must never arrive as a value."""
    from backend.data.realcdp import parse_cell

    assert parse_cell(cell) == (None, status)


def test_cdp_unknown_cell_is_reported_not_silently_dropped():
    from backend.data.realcdp import parse_cell

    assert parse_cell("Something CDP started printing in 2027") == ("", "unrecognised")


def test_did_not_disclose_never_reaches_a_rater_channel():
    """The overlay must not turn a non-disclosure into a CDP letter on any row."""
    from backend.data.realcdp import disclosure_status, overlay

    declined = list(disclosure_status())
    if not declined:
        pytest.skip("no non-disclosing company in the cache")
    rows = [RaterRow(cid, YEAR, "BBB", 30.0, 50.0) for cid in declined]
    for row in overlay(rows):
        if row.company_id not in declined:
            continue          # the overlay also lands scored companies; only check these
        assert row.cdp_letter is None, f"{row.company_id} was given a CDP letter it never earned"


def test_cdp_scores_land_on_their_own_assessment_year():
    from backend.data.realcdp import overlay, scored_by_year

    by_year = scored_by_year()
    if not by_year:
        pytest.skip("no CDP scores cached")
    cid, years = next(iter(by_year.items()))
    year = next(iter(years))
    rows = [r for r in overlay([RaterRow(cid, year - 1, None, None, None)])
            if r.company_id == cid]
    at = {r.year: r for r in rows}
    assert at[year].cdp_letter == years[year]["cdp"]     # a row is created for its year
    assert at[year - 1].cdp_letter is None               # the neighbouring year is untouched


def test_report_disclosed_cdp_wins_over_the_table():
    """Precedence: a verbatim citation beats a table cell. Any real disagreement has to be
    reported rather than silently resolved."""
    from backend.data.realcdp import discrepancies
    from backend.engine import ingest

    ds = ingest.load()
    for clash in discrepancies():
        assert clash["resolved_to"] == clash["report"]
        row = next(r for r in ds.raters
                   if r.company_id == clash["company_id"] and r.year == clash["year"])
        assert row.cdp_letter == clash["report"]


def test_hand_entry_lands_on_the_year_the_reader_recorded(_isolated_db):
    """A 2025 S&P score must not be filed under the 2023 analysis year."""
    from backend.engine.manual_raters import real_keys_by_company_year, set_manual_rater

    set_manual_rater("D05", "sp", "65", "2026-08-01",
                     "https://www.spglobal.com/esg/scores/x", assessment_year=2025)
    assert real_keys_by_company_year()["D05"] == {2025: ["sp"]}
    rows = [r for r in overlay([RaterRow("D05", YEAR, None, None, None)])
            if r.company_id == "D05"]
    at = {r.year: r for r in rows}
    assert at[2025].sp_global == 65.0
    assert at[YEAR].sp_global is None          # the analysis year is untouched


def test_hand_entry_defaults_to_the_analysis_year(_isolated_db):
    from backend.engine.manual_raters import real_keys_by_company_year

    _set(rater="sp", value="65")
    assert real_keys_by_company_year()["D05"] == {YEAR: ["sp"]}


@pytest.mark.parametrize("year", [1999, 2100, "soon"])
def test_hand_entry_rejects_an_impossible_year(_isolated_db, year):
    from backend.engine.manual_raters import set_manual_rater

    with pytest.raises(ValueError):
        set_manual_rater("D05", "sp", "65", "2026-08-01",
                         "https://example.com/x", assessment_year=year)
