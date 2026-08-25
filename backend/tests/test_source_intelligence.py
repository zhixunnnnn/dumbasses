from __future__ import annotations

from backend.engine import config
from backend.engine.db import bootstrap
from backend.engine.source_intelligence import (
    Candidate,
    canonicalize_url,
    classify_domain,
    get_company_intelligence,
    group_claims,
    initialize_source_registry,
    list_source_registry,
    persist_company_research,
)


def candidate(url: str, source_class: str, title: str = "DBS ESG") -> Candidate:
    domain = url.split("//", 1)[1].split("/", 1)[0]
    return Candidate(
        company_id="D05",
        title=title,
        url=url,
        snippet=title,
        provider="test",
        domain=domain,
        source_class=source_class,
    )


def test_canonical_url_removes_tracking_and_normalizes_host():
    result = canonicalize_url(
        "HTTPS://WWW.DBS.COM/sustainability/?utm_source=test&b=2&a=1#section"
    )
    assert result == "https://dbs.com/sustainability?a=1&b=2"


def test_builtin_registry_classifies_subdomains(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "research.sqlite3")
    initialize_source_registry()

    assert classify_domain("sustainability.egco.com") == "verified"
    assert classify_domain("reddit.com") == "community"
    assert classify_domain("unknown.example") == "non_verified"


def test_claims_are_grouped_across_independent_sources():
    from backend.engine.source_intelligence import ClaimCandidate

    text = "DBS Group uses renewable energy for its Singapore operations and reduced emissions."
    claims = [
        ClaimCandidate("D05", text, "renewable_energy", 1, candidate("https://dbs.com/a", "verified")),
        ClaimCandidate("D05", text + " in 2025", "renewable_energy", 1, candidate("https://news.example/a", "non_verified")),
    ]

    grouped = group_claims(claims)

    assert len(grouped) == 1
    assert grouped[0]["verification"] == "verified"
    assert grouped[0]["independent_domains"] == 2


def test_persistence_updates_renewable_status_and_promotion_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "research.sqlite3")
    initialize_source_registry()
    conn = bootstrap()
    conn.execute(
        "INSERT INTO universe(company_id, ticker, name, country, exchange, sector, sasb_industry, scope) "
        "VALUES ('D05', 'D05.SI', 'DBS Group', 'Singapore', 'SGX', 'Financials', 'Banks', 'demo')"
    )
    conn.commit()
    conn.close()
    now_pages = [
        (candidate("https://dbs.com/renewable", "verified"), "DBS renewable evidence"),
        (candidate("https://reuters.com/dbs-emissions", "verified"), "DBS emissions evidence"),
        (candidate("https://esg-broad.example/dbs", "non_verified"), "Matching evidence"),
    ]
    claims = [
        {
            "claim_id": "renewable-claim",
            "company_id": "D05",
            "claim_text": "DBS Group uses renewable energy for its Singapore operations.",
            "topic": "renewable_energy",
            "verification": "verified",
            "sentiment": 1.0,
            "sources": [now_pages[0][0], now_pages[2][0]],
            "independent_domains": 2,
        },
        {
            "claim_id": "emissions-claim",
            "company_id": "D05",
            "claim_text": "DBS Group reduced operational carbon emissions during the year.",
            "topic": "emissions",
            "verification": "verified",
            "sentiment": 1.0,
            "sources": [now_pages[1][0], now_pages[2][0]],
            "independent_domains": 2,
        },
    ]
    persist_company_research(
        "D05",
        now_pages,
        claims,
        {"retainRawDays": 30},
    )

    intelligence = get_company_intelligence("D05")
    registry = list_source_registry()
    promotion = next(item for item in registry["candidates"] if item["domain"] == "esg-broad.example")

    assert intelligence["renewable"]["renewable_status"] == "Verified"
    assert intelligence["renewable"]["emissions_trend"] == "Falling"
    assert promotion["status"] == "pending"
    assert promotion["matching_claims"] == 2
    assert set(promotion["matched_verified_domains"]) == {"dbs.com", "reuters.com"}
