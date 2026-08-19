"""Normalized search and page-fetch adapters for external scraper providers.

Credentials are read only from environment variables. Provider selection is
stored separately in SQLite so the Settings page never receives secrets.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


SCRAPEDO_API_URL = "https://api.scrape.do/"
SCRAPEDO_SEARCH_URL = "https://api.scrape.do/plugin/google/search"
OXYLABS_API_URL = "https://realtime.oxylabs.io/v1/queries"

PROVIDER_LABELS = {
    "brightdata": "Bright Data",
    "scrapedo": "Scrape.do",
    "oxylabs": "Oxylabs",
    "crawl4ai_searxng": "Crawl4AI + SearXNG",
}


@dataclass(frozen=True)
class ProviderSearchResult:
    title: str
    url: str
    snippet: str | None
    source: str


@dataclass(frozen=True)
class ProviderFetchResult:
    url: str
    content: bytes
    text: str
    content_type: str
    source: str


def provider_availability() -> dict[str, dict[str, Any]]:
    brightdata = bool(
        _env_first(
            "BRIGHTDATA_API_KEY",
            "BRIGHT_DATA_API_KEY",
            "BRIGHTDATA_TOKEN",
            "BRIGHT_DATA_TOKEN",
            "BRIGHTDATA_PROXY",
            "BRIGHTDATA_BROWSER_WSS",
        )
    )
    statuses = {
        "brightdata": (brightdata, None if brightdata else "Bright Data credentials are missing."),
        "scrapedo": (
            bool(os.environ.get("SCRAPEDO_API_TOKEN")),
            None if os.environ.get("SCRAPEDO_API_TOKEN") else "SCRAPEDO_API_TOKEN is missing.",
        ),
        "oxylabs": (
            bool(os.environ.get("OXYLABS_USERNAME") and os.environ.get("OXYLABS_PASSWORD")),
            None
            if os.environ.get("OXYLABS_USERNAME") and os.environ.get("OXYLABS_PASSWORD")
            else "OXYLABS_USERNAME or OXYLABS_PASSWORD is missing.",
        ),
        "crawl4ai_searxng": (
            bool(os.environ.get("SEARXNG_BASE_URL") and os.environ.get("CRAWL4AI_BASE_URL")),
            None
            if os.environ.get("SEARXNG_BASE_URL") and os.environ.get("CRAWL4AI_BASE_URL")
            else "SEARXNG_BASE_URL or CRAWL4AI_BASE_URL is missing.",
        ),
    }
    return {
        key: {
            "id": key,
            "label": PROVIDER_LABELS[key],
            "available": available,
            "reason": reason,
        }
        for key, (available, reason) in statuses.items()
    }


async def search_scrapedo(
    query: str,
    max_results: int,
    client: httpx.AsyncClient,
) -> list[ProviderSearchResult]:
    token = os.environ.get("SCRAPEDO_API_TOKEN")
    if not token:
        return []
    response = await client.get(
        SCRAPEDO_SEARCH_URL,
        params={
            "token": token,
            "q": query,
            "gl": "sg",
            "hl": "en",
            "device": "desktop",
        },
    )
    response.raise_for_status()
    return _normalize_search_payload(response.json(), "scrapedo_search", max_results)


async def fetch_scrapedo(
    url: str,
    client: httpx.AsyncClient,
) -> ProviderFetchResult:
    token = os.environ.get("SCRAPEDO_API_TOKEN")
    if not token:
        raise RuntimeError("Scrape.do is not configured.")

    response = await client.get(
        SCRAPEDO_API_URL,
        params={"token": token, "url": url, "geoCode": "sg"},
    )
    response.raise_for_status()
    if _looks_blocked(response.text):
        response = await client.get(
            SCRAPEDO_API_URL,
            params={
                "token": token,
                "url": url,
                "geoCode": "sg",
                "render": "true",
                "waitUntil": "domcontentloaded",
            },
        )
        response.raise_for_status()
    return ProviderFetchResult(
        url=url,
        content=response.content,
        text=response.text,
        content_type=response.headers.get("content-type", ""),
        source="scrapedo",
    )


async def search_oxylabs(
    query: str,
    max_results: int,
    client: httpx.AsyncClient,
) -> list[ProviderSearchResult]:
    username, password = _oxylabs_credentials()
    if not username or not password:
        return []
    response = await client.post(
        OXYLABS_API_URL,
        auth=(username, password),
        json={
            "source": "google_search",
            "query": query,
            "geo_location": "Singapore",
            "parse": True,
        },
    )
    response.raise_for_status()
    content = _oxylabs_content(response.json())
    return _normalize_search_payload(content, "oxylabs_search", max_results)


async def fetch_oxylabs(
    url: str,
    client: httpx.AsyncClient,
) -> ProviderFetchResult:
    username, password = _oxylabs_credentials()
    if not username or not password:
        raise RuntimeError("Oxylabs is not configured.")
    response = await client.post(
        OXYLABS_API_URL,
        auth=(username, password),
        json={
            "source": "universal",
            "url": url,
            "geo_location": "Singapore",
        },
    )
    response.raise_for_status()
    payload = response.json()
    content = _oxylabs_content(payload)
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    if _looks_blocked(text):
        response = await client.post(
            OXYLABS_API_URL,
            auth=(username, password),
            json={
                "source": "universal",
                "url": url,
                "geo_location": "Singapore",
                "render": "html",
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = _oxylabs_content(payload)
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    resolved_url = url
    results = payload.get("results") if isinstance(payload, dict) else None
    if isinstance(results, list) and results and isinstance(results[0], dict):
        resolved_url = str(results[0].get("url") or url)
    encoded = text.encode("utf-8")
    return ProviderFetchResult(
        url=resolved_url,
        content=encoded,
        text=text,
        content_type="text/html; charset=utf-8",
        source="oxylabs",
    )


async def search_searxng(
    query: str,
    max_results: int,
    client: httpx.AsyncClient,
) -> list[ProviderSearchResult]:
    base_url = os.environ.get("SEARXNG_BASE_URL", "").rstrip("/")
    if not base_url:
        return []
    response = await client.get(
        f"{base_url}/search",
        params={
            "q": query,
            "format": "json",
            "language": "en",
            "categories": "general,news",
            "safesearch": 1,
        },
    )
    response.raise_for_status()
    return _normalize_search_payload(response.json(), "searxng_search", max_results)


async def fetch_crawl4ai(
    url: str,
    client: httpx.AsyncClient,
) -> ProviderFetchResult:
    base_url = os.environ.get("CRAWL4AI_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("Crawl4AI is not configured.")
    response = await client.post(
        f"{base_url}/crawl",
        json={
            "urls": [url],
            "browser_config": {
                "headless": True,
                "text_mode": True,
            },
            "crawler_config": {
                "cache_mode": "bypass",
                "page_timeout": 60000,
                "wait_until": "domcontentloaded",
            },
        },
    )
    response.raise_for_status()
    payload = response.json()
    result = _crawl4ai_result(payload)
    text = _crawl4ai_text(result)
    if not text:
        raise RuntimeError("Crawl4AI returned no readable content.")
    resolved_url = str(result.get("url") or url) if isinstance(result, dict) else url
    encoded = text.encode("utf-8")
    return ProviderFetchResult(
        url=resolved_url,
        content=encoded,
        text=text,
        content_type="text/plain; charset=utf-8",
        source="crawl4ai",
    )


def _normalize_search_payload(
    payload: Any,
    source: str,
    max_results: int,
) -> list[ProviderSearchResult]:
    items = _find_search_items(payload)
    output: list[ProviderSearchResult] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("href")
        if not isinstance(url, str) or not _is_http_url(url):
            continue
        key = url.split("#", 1)[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        title = str(item.get("title") or item.get("name") or url)[:200]
        snippet = item.get("description") or item.get("snippet") or item.get("desc")
        output.append(
            ProviderSearchResult(
                title=title,
                url=url,
                snippet=str(snippet)[:500] if snippet else None,
                source=source,
            )
        )
        if len(output) >= max_results:
            break
    return output


def _find_search_items(payload: Any) -> list[Any]:
    if isinstance(payload, str):
        try:
            return _find_search_items(json.loads(payload))
        except json.JSONDecodeError:
            return []
    if isinstance(payload, list):
        if any(isinstance(item, dict) and _item_has_url(item) for item in payload):
            return payload
        for item in payload:
            found = _find_search_items(item)
            if found:
                return found
        return []
    if not isinstance(payload, dict):
        return []
    for key in ("organic", "organic_results", "organicResults", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list) and any(
            isinstance(item, dict) and _item_has_url(item) for item in value
        ):
            return value
    for value in payload.values():
        found = _find_search_items(value)
        if found:
            return found
    return []


def _oxylabs_content(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return payload
    content = results[0].get("content")
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content if content is not None else payload


def _crawl4ai_result(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if not isinstance(payload, dict):
        return {}
    results = payload.get("results") or payload.get("data")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    if isinstance(results, dict):
        return results
    return payload


def _crawl4ai_text(result: dict[str, Any]) -> str:
    markdown = result.get("markdown")
    if isinstance(markdown, dict):
        for key in ("fit_markdown", "raw_markdown", "markdown_with_citations"):
            if markdown.get(key):
                return str(markdown[key])
    if isinstance(markdown, str):
        return markdown
    for key in ("cleaned_html", "html", "text"):
        if result.get(key):
            return str(result[key])
    return ""


def _looks_blocked(text: str) -> bool:
    sample = text[:5000].lower()
    return len(text.strip()) < 300 or any(
        marker in sample
        for marker in (
            "access denied",
            "captcha",
            "cf-chl-",
            "enable javascript and cookies",
            "temporarily blocked",
        )
    )


def _item_has_url(item: dict[str, Any]) -> bool:
    return any(isinstance(item.get(key), str) for key in ("url", "link", "href"))


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _oxylabs_credentials() -> tuple[str | None, str | None]:
    return os.environ.get("OXYLABS_USERNAME"), os.environ.get("OXYLABS_PASSWORD")


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None
