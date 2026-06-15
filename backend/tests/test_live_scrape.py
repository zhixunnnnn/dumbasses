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
