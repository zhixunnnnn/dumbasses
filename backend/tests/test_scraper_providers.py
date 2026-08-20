from __future__ import annotations

import asyncio
import json

import httpx

import backend.app.agent as agent_module
from backend.app.agent import AssistantSource, WebTools
from backend.engine import config
from backend.engine.scrape_settings import get_scrape_settings, save_scrape_settings
from backend.engine.scraper_providers import (
    ProviderSearchResult,
    fetch_oxylabs,
    fetch_scrapedo,
    fetch_crawl4ai,
    provider_availability,
    search_oxylabs,
    search_scrapedo,
    search_searxng,
)


class FakeResponse:
    def __init__(
        self,
        payload=None,
        *,
        text: str | None = None,
        status_code: int = 200,
        url: str = "https://provider.test/",
    ) -> None:
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)
        self.content = self.text.encode("utf-8")
        self.status_code = status_code
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.url = url
        self.request = httpx.Request("GET", url)

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "provider error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class FakeClient:
    def __init__(self, *, get_responses=None, post_responses=None) -> None:
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)


def test_scrapedo_search_normalizes_structured_google_results(monkeypatch):
    monkeypatch.setenv("SCRAPEDO_API_TOKEN", "test-token")
    client = FakeClient(
        get_responses=[
            FakeResponse(
                {
                    "organic_results": [
                        {
                            "title": "DBS sustainability report",
                            "link": "https://www.dbs.com/sustainability/report",
                            "snippet": "Renewable electricity and emissions data.",
                        }
                    ]
                }
            )
        ]
    )

    results = asyncio.run(search_scrapedo("DBS ESG", 10, client))

    assert len(results) == 1
    assert results[0].source == "scrapedo_search"
    assert results[0].url == "https://www.dbs.com/sustainability/report"
    assert client.get_calls[0][1]["params"]["q"] == "DBS ESG"


def test_scrapedo_fetch_retries_with_render_when_first_page_is_blocked(monkeypatch):
    monkeypatch.setenv("SCRAPEDO_API_TOKEN", "test-token")
    client = FakeClient(
        get_responses=[
            FakeResponse(text="Access denied"),
            FakeResponse(text="<html><title>Loaded</title><body>" + "data " * 100 + "</body></html>"),
        ]
    )

    result = asyncio.run(fetch_scrapedo("https://example.com/esg", client))

    assert result.source == "scrapedo"
    assert len(client.get_calls) == 2
    assert client.get_calls[1][1]["params"]["render"] == "true"


def test_oxylabs_search_and_fetch_parse_realtime_envelope(monkeypatch):
    monkeypatch.setenv("OXYLABS_USERNAME", "test-user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "test-password")
    search_client = FakeClient(
        post_responses=[
            FakeResponse(
                {
                    "results": [
                        {
                            "content": {
                                "organic": [
                                    {
                                        "title": "SGX sustainability disclosure",
                                        "url": "https://www.sgx.com/esg/disclosure",
                                        "desc": "Primary exchange guidance.",
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
        ]
    )
    fetch_client = FakeClient(
        post_responses=[
            FakeResponse(
                {
                    "results": [
                        {
                            "url": "https://www.sgx.com/esg/disclosure",
                            "content": "<html><body>" + "guidance " * 100 + "</body></html>",
                        }
                    ]
                }
            )
        ]
    )

    results = asyncio.run(search_oxylabs("SGX ESG", 10, search_client))
    fetched = asyncio.run(fetch_oxylabs("https://www.sgx.com/esg/disclosure", fetch_client))

    assert results[0].source == "oxylabs_search"
    assert results[0].url == "https://www.sgx.com/esg/disclosure"
    assert fetched.source == "oxylabs"
    assert "guidance" in fetched.text
    assert search_client.post_calls[0][1]["json"]["source"] == "google_search"
    assert fetch_client.post_calls[0][1]["json"]["source"] == "universal"


def test_searxng_search_and_crawl4ai_fetch(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://search.internal")
    monkeypatch.setenv("CRAWL4AI_BASE_URL", "https://crawl.internal")
    search_client = FakeClient(get_responses=[FakeResponse({
        "results": [{
            "title": "DBS sustainability",
            "url": "https://dbs.com/sustainability",
            "content": "Official report and renewable energy information.",
        }]
    })])
    # /md is the primary endpoint: flat body, stable across Crawl4AI releases.
    crawl_client = FakeClient(post_responses=[FakeResponse({
        "url": "https://dbs.com/sustainability",
        "markdown": "DBS sustainability evidence",
        "success": True,
    })])

    results = asyncio.run(search_searxng("DBS ESG", 10, search_client))
    fetched = asyncio.run(fetch_crawl4ai("https://dbs.com/sustainability", crawl_client))

    assert results[0].source == "searxng_search"
    assert results[0].url == "https://dbs.com/sustainability"
    assert fetched.source == "crawl4ai"
    assert "sustainability evidence" in fetched.text
    assert search_client.get_calls[0][1]["params"]["format"] == "json"
    assert crawl_client.post_calls[0][0].endswith("/md")
    assert crawl_client.post_calls[0][1]["json"]["url"] == "https://dbs.com/sustainability"


def test_crawl4ai_falls_back_to_crawl_when_md_is_unavailable(monkeypatch):
    """Older/trimmed Crawl4AI builds have no /md route. The adapter must retry via
    /crawl rather than reporting the page as unfetchable."""
    monkeypatch.setenv("CRAWL4AI_BASE_URL", "https://crawl.internal")
    client = FakeClient(post_responses=[
        FakeResponse({"detail": "Not Found"}, status_code=404),
        FakeResponse({
            "results": [{
                "url": "https://dbs.com/sustainability",
                "markdown": {"fit_markdown": "DBS sustainability evidence"},
            }]
        }),
    ])

    fetched = asyncio.run(fetch_crawl4ai("https://dbs.com/sustainability", client))

    assert "sustainability evidence" in fetched.text
    assert client.post_calls[0][0].endswith("/md")
    assert client.post_calls[1][0].endswith("/crawl")
    assert client.post_calls[1][1]["json"]["urls"] == ["https://dbs.com/sustainability"]
    # The config objects must carry the explicit serialization wrapper the server
    # deserializes on every release.
    assert client.post_calls[1][1]["json"]["browser_config"]["type"] == "BrowserConfig"


def test_base_url_is_normalized_from_a_pasted_endpoint(monkeypatch):
    """The base-URL bug: a value pasted with no scheme, a trailing slash, or an
    endpoint path used to produce unresolvable request URLs."""
    from backend.engine.scraper_providers import normalize_base_url

    assert normalize_base_url("  searxng.up.railway.app/ ") == "https://searxng.up.railway.app"
    assert normalize_base_url("http://localhost:11235/crawl") == "http://localhost:11235"
    assert normalize_base_url("crawl4ai.railway.internal:11235") == "http://crawl4ai.railway.internal:11235"
    assert normalize_base_url("") == ""
    assert normalize_base_url("not a url") == ""


def test_searxng_reports_a_blocked_json_api_instead_of_empty_results(monkeypatch):
    """A limiter-enabled instance 403s the JSON API. Returning [] there looks like
    'no results found', which hides the misconfiguration."""
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://search.internal")
    client = FakeClient(get_responses=[FakeResponse({}, status_code=403)])

    try:
        asyncio.run(search_searxng("DBS ESG", 10, client))
    except RuntimeError as exc:
        assert "limiter" in str(exc)
    else:
        raise AssertionError("a blocked JSON API must raise, not return []")


def test_provider_availability_never_returns_credentials(monkeypatch):
    monkeypatch.setenv("SCRAPEDO_API_TOKEN", "secret-token")
    monkeypatch.setenv("OXYLABS_USERNAME", "secret-user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "secret-password")

    serialized = json.dumps(provider_availability())

    assert "secret-token" not in serialized
    assert "secret-user" not in serialized
    assert "secret-password" not in serialized
    assert provider_availability()["scrapedo"]["available"] is True
    assert provider_availability()["oxylabs"]["available"] is True


def test_scrape_settings_are_persisted_without_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "settings.sqlite3")
    monkeypatch.setenv("SCRAPEDO_API_TOKEN", "settings-secret-token")
    monkeypatch.setenv("OXYLABS_USERNAME", "settings-secret-user")
    monkeypatch.setenv("OXYLABS_PASSWORD", "settings-secret-password")
    saved = save_scrape_settings(
        {
            "providers": {"brightdata": False, "scrapedo": True},
            "frequency": "daily",
            "timezone": "Asia/Singapore",
            "runAt": "06:00",
            "retainRawDays": 30,
        }
    )
    loaded = get_scrape_settings()

    assert saved["frequency"] == "daily"
    assert loaded["providers"]["brightdata"] is False
    assert loaded["providers"]["scrapedo"] is True
    serialized = json.dumps(loaded)
    assert "settings-secret-token" not in serialized
    assert "settings-secret-user" not in serialized
    assert "settings-secret-password" not in serialized
    assert "apiToken" not in serialized


def test_webtools_merges_and_deduplicates_enabled_provider_results(monkeypatch):
    tools = WebTools()
    monkeypatch.setattr(agent_module, "enabled_providers", lambda: ["scrapedo", "oxylabs"])
    monkeypatch.setattr(agent_module, "_disk_cache_get", lambda _key: None)
    monkeypatch.setattr(agent_module, "_disk_cache_set", lambda _key, _value: None)

    async def fake_scrapedo(query, max_results, client):
        return [
            ProviderSearchResult("DBS report", "https://dbs.com/report", "Primary", "scrapedo_search")
        ]

    async def fake_oxylabs(query, max_results, client):
        return [
            ProviderSearchResult("Duplicate", "https://dbs.com/report/", "Same", "oxylabs_search"),
            ProviderSearchResult("Reuters", "https://reuters.com/dbs", "News", "oxylabs_search"),
        ]

    async def fake_native(query, max_results):
        return [
            AssistantSource(
                title="CNA",
                url="https://channelnewsasia.com/dbs",
                snippet="Coverage",
                source="native_search",
            )
        ]

    monkeypatch.setattr(agent_module, "search_scrapedo", fake_scrapedo)
    monkeypatch.setattr(agent_module, "search_oxylabs", fake_oxylabs)
    monkeypatch.setattr(tools, "_search_native", fake_native)

    result = asyncio.run(tools.search("provider fanout unique query", 10))

    assert len(result["results"]) == 3
    assert result["providers"] == ["scrapedo_search", "oxylabs_search", "native_search"]
