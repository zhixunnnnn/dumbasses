from __future__ import annotations

import backend.app.agent as agent_module
from backend.data import scrape
from backend.data import realclaims
from backend.engine.db import bootstrap


def test_scrape_news_uses_request_api_when_scraping_browser_is_unavailable(
    monkeypatch,
    tmp_path,
):
    conn = bootstrap(tmp_path / "news.sqlite3")
    conn.execute(
        "INSERT INTO universe VALUES (?,?,?,?,?,?,?,?)",
        (
            "D05",
            "D05.SI",
            "DBS Group",
            "Singapore",
            "SGX",
            "Financials",
            "Commercial Banks",
            "demo",
        ),
    )
    conn.commit()

    queries: list[str] = []

    class FakeWebTools:
        async def search(self, query: str, max_results: int = 10):
            queries.append(query)
            return {
                "results": [
                    {
                        "title": (
                            "DBS Group expands sustainable finance and net zero "
                            "transition targets"
                        ),
                        "url": "https://example.com/dbs-esg",
                        "snippet": "DBS sustainability ESG climate progress",
                        "source": "bright_data",
                    },
                    {
                        "title": "Generic market update without a company match",
                        "url": "https://example.com/noise",
                        "snippet": "Market update",
                        "source": "bright_data",
                    },
                ]
            }

    def fail_browser_collect(*args, **kwargs):
        raise AssertionError("Scraping Browser should not be required")

    monkeypatch.setattr(agent_module, "WebTools", FakeWebTools)
    monkeypatch.setattr(scrape.brightdata, "browser_collect", fail_browser_collect)
    monkeypatch.setattr(scrape.config, "OUT_DIR", tmp_path)
    # exercise the deterministic keyword path (no network LLM call during the test)
    monkeypatch.setattr(scrape, "_news_llm_client", lambda: None)

    result = scrape.scrape_news(conn, offline=False)

    assert queries == [
        "DBS Group sustainability ESG news",
        "DBS Group stock earnings results news",
    ]
    assert result["companies"][0]["company_id"] == "D05"
    assert result["companies"][0]["n_items"] == 1
    assert result["companies"][0]["positive"] == 1
    assert result["companies"][0]["headlines"][0]["url"] == "https://example.com/dbs-esg"
    assert result["source"] == "Bright Data Request API - Bing News"


def test_real_claims_default_subset_covers_all_ten_companies():
    assert set(realclaims.DEFAULT_SUBSET) == set(realclaims.DOMAINS)
    assert len(realclaims.DEFAULT_SUBSET) == 10


def test_engine_config_loads_repo_root_env_for_brightdata():
    from backend.engine import config

    src = (config.BACKEND_DIR / "engine" / "config.py").read_text(encoding="utf-8")

    assert "BACKEND_DIR.parent / \".env\"" in src
    assert "BACKEND_DIR / \".env\"" in src


def test_scrape_prices_falls_back_to_marketwatch_and_replaces_existing_rows(
    monkeypatch,
    tmp_path,
):
    conn = bootstrap(tmp_path / "prices.sqlite3")
    conn.execute(
        "INSERT INTO universe VALUES (?,?,?,?,?,?,?,?)",
        (
            "O39",
            "O39.SI",
            "OCBC",
            "Singapore",
            "SGX",
            "Financials",
            "Commercial Banks",
            "demo",
        ),
    )
    conn.execute(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?)",
        ("O39", "2018-12-30", 1, 1, 1, 1, 10),
    )
    conn.commit()

    calls: list[str] = []

    def fake_fetch(source: str, key: str, url: str, **kwargs):
        calls.append(source)
        if key == "^STI":
            return None
        if source == "yahoo_prices":
            return "Request Failed (bad_endpoint): robots.txt"
        if source == "marketwatch_prices":
            return (
                "Date,Open,High,Low,Close,Volume\n"
                '12/29/2023,"12.67","13.05","12.59","13.00","21,550,200"\n'
                '12/22/2023,"12.30","12.68","12.27","12.66","19,298,164"\n'
            )
        raise AssertionError(source)

    monkeypatch.setattr(scrape.brightdata, "fetch_or_cache", fake_fetch)
    monkeypatch.setattr(scrape, "_fetch_native_yahoo", lambda url: None)

    written = scrape.scrape_prices(conn, offline=False)

    rows = conn.execute(
        "SELECT week_date, open, close, volume FROM prices WHERE company_id=? "
        "ORDER BY week_date",
        ("O39",),
    ).fetchall()
    assert written == 2
    assert calls[:2] == ["yahoo_prices", "marketwatch_prices"]
    assert [row["week_date"] for row in rows] == ["2023-12-22", "2023-12-29"]
    assert rows[0]["open"] == 12.3
    assert rows[1]["close"] == 13.0
    assert rows[1]["volume"] == 21550200


def test_scrape_prices_uses_native_yahoo_when_brightdata_blocks(
    monkeypatch,
    tmp_path,
):
    conn = bootstrap(tmp_path / "prices.sqlite3")
    conn.execute(
        "INSERT INTO universe VALUES (?,?,?,?,?,?,?,?)",
        (
            "U11",
            "U11.SI",
            "UOB",
            "Singapore",
            "SGX",
            "Financials",
            "Commercial Banks",
            "demo",
        ),
    )
    conn.commit()

    native_body = """
    {"chart":{"result":[{"timestamp":[1703808000],"indicators":{"quote":[{
      "open":[27.6],"high":[28.64],"low":[27.48],"close":[28.45],"volume":[10198100]
    }]}}]}}
    """
    marketwatch_called = False

    def fake_fetch(source: str, key: str, url: str, **kwargs):
        nonlocal marketwatch_called
        if key == "^STI":
            return None
        if source == "marketwatch_prices":
            marketwatch_called = True
        return "Request Failed (bad_endpoint): robots.txt"

    monkeypatch.setattr(scrape.brightdata, "fetch_or_cache", fake_fetch)
    monkeypatch.setattr(
        scrape,
        "_fetch_native_yahoo",
        lambda url: None if "%5ESTI" in url else native_body,
    )

    written = scrape.scrape_prices(conn, offline=False)

    row = conn.execute(
        "SELECT week_date, open, high, low, close, volume FROM prices WHERE company_id=?",
        ("U11",),
    ).fetchone()
    assert written == 1
    assert marketwatch_called is False
    assert row["week_date"] == "2023-12-29"
    assert row["close"] == 28.45


def test_real_claim_rows_fall_back_when_openrouter_extraction_fails():
    class FailingClient:
        def extract(self, text: str):
            raise ValueError("bad model response")

    report = {
        "title": "Example Sustainability Report",
        "url": "https://example.com/report.pdf",
        "text": (
            "The company improved energy efficiency and reduced carbon "
            "emissions across its portfolio."
        ),
    }

    rows = realclaims._claim_rows(
        "C09",
        "Real Estate",
        report,
        FailingClient(),
    )

    assert rows
    assert rows[0]["state"] == "ASSERTED"
    assert rows[0]["source_url"] == "https://example.com/report.pdf"


# --- report-year stamping: rows carry the REPORT's year, never the analysis year ---
def test_report_year_is_derived_from_the_report_not_the_config():
    assert realclaims._report_year({"url": "https://x.com/dbs_sr2024.pdf"}) == 2024
    # fiscal spans resolve to the later year (SIA's "2425" report is FY2024/25)
    assert realclaims._report_year({"url": "https://x.com/sustainabilityreport2425.pdf"}) == 2025
    assert realclaims._report_year({"url": "https://x.com/report.pdf",
                                    "title": "Acme Sustainability Report 2021"}) == 2021
    # nothing datable anywhere -> None, never a guess
    assert realclaims._report_year({"url": "https://x.com/report.pdf", "title": "Acme SR",
                                    "text": "no year here"}) is None


def test_extracted_rows_are_stamped_with_the_report_year():
    rows = realclaims._claim_rows(
        "C09", "Real Estate",
        {"title": "CDL Sustainability Report 2021",
         "url": "https://example.com/isr2021.pdf",
         "report_year": 2021,
         "text": "The company improved energy efficiency and reduced carbon emissions."},
        realclaims.MockLLMClient(),
    )
    assert rows
    assert all(r["report_year"] == 2021 for r in rows)


def test_per_year_cache_path_and_miss_envelope(tmp_path, monkeypatch):
    monkeypatch.setattr(realclaims.config, "CACHE_DIR", tmp_path)
    assert realclaims.cache_path_for("D05", 2021).name == "D05_2021.json"
    assert realclaims.cache_path_for("D05", None).name == "D05.json"
    realclaims.record_miss("D05", 2019)
    assert realclaims.read_cache("D05", 2019) == {"rows": [], "miss": True, "report_year": 2019}
    assert realclaims.cached_claims_for("D05", year=2019) is None


def test_press_releases_and_filings_are_not_accepted_as_the_report():
    """SERP for "<name> sustainability report <year>" returns credit research, press
    releases and financial statements; those misattribute the year, so they are out."""
    assert realclaims._looks_like_report(
        "https://www.dbs.com/annualreports/2024/i/pdf/dbs_sr2024.pdf", "dbs sr2024")
    assert not realclaims._looks_like_report(
        "https://media.sembcorp.com/data/cms/ar/ar2025/assets/pdf/Consolidated_Financial_Statements.pdf",
        "Consolidated Financial Statements")
    assert not realclaims._looks_like_report(
        "https://www.ocbc.com/pdf/Credit%20Research/2025/oc.pdf", "OCBC Credit Research Sustainable Finance")
    assert not realclaims._looks_like_report(
        "https://www.uobgroup.com/web-resources/pdf/newsroom/2025/uob-nature.pdf", "uob nature risks")


def test_a_peers_report_is_never_accepted_for_this_company():
    """SERP for "CapitaLand sustainability report 2025" returned Mapletree's annual
    report; extracting from it would attribute a peer's claims to CapitaLand."""
    assert not realclaims._looks_like_report(
        "https://www.mapletree.com.sg/uploads/2025/01/Sustainability-Report-2025.pdf",
        "Mapletree Sustainability Report", "capitaland.com")
    # a company's own sustainability microsite still counts as the company
    assert realclaims._looks_like_report(
        "https://cdlsustainability.com/pdf/CDL_ISR_2025.pdf", "CDL ISR 2025", "cdl.com.sg")


def test_two_digit_report_stamps_are_read_as_years():
    """`keppel-...-ar-21-full-report.pdf` was landing in 2022 because its year lived in
    a two-digit stamp the parser could not see."""
    assert realclaims._years_in("keppel-corporation-ar-21-full-report.pdf") == {2021}
    assert realclaims._years_in("ghg-fy20-wilmar-ey-assurance.pdf") == {2020}
    # ...without breaking the four-digit stamps that already worked
    assert realclaims._years_in("dbs_sr2024.pdf") == {2024}
    assert realclaims._years_in("CLI-GSR-2024.pdf") == {2024}


def test_instrument_level_documents_are_not_the_years_report():
    """A green-bond report or a third-party second opinion covers one instrument, not
    the company-year, so its claims must not be filed as that year's disclosure."""
    for url in ("https://www.dbs.com/x/DBS_Green_Bond_Report_August_2022.pdf",
                "https://www.ocbc.com/assets/pdf/Green%20Bond/Second%20Opinion.pdf",
                "https://www.dbs.com/x/2020%20Sustainability%20Fact%20Sheet.pdf"):
        assert not realclaims._looks_like_report(url, "sustainability", "")
