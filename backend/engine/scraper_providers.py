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

# Self-hosted endpoints. The URL is a setting, not a secret, so it is editable from
# the Settings page and persisted alongside the other scraping settings; the
# environment variable stays as the deployment-level default.
SEARXNG_URL_KEY = "searxngBaseUrl"
CRAWL4AI_URL_KEY = "crawl4aiBaseUrl"

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
            bool(searxng_base_url() and crawl4ai_base_url()),
            None
            if searxng_base_url() and crawl4ai_base_url()
            else "Set the SearXNG and Crawl4AI base URLs in Settings "
            "(or SEARXNG_BASE_URL / CRAWL4AI_BASE_URL).",
        ),
    }
    endpoints = {"searxng": searxng_base_url(), "crawl4ai": crawl4ai_base_url()}
    return {
        key: {
            "id": key,
            "label": PROVIDER_LABELS[key],
            "available": available,
            "reason": reason,
            **({"endpoints": endpoints} if key == "crawl4ai_searxng" else {}),
        }
        for key, (available, reason) in statuses.items()
    }


# --------------------------------------------------------------------------- #
# Base URL resolution — the bug this fixes: a URL typed without a scheme, with a
# trailing slash, or with a path suffix produced requests like
# "myhost.up.railway.app//search", which never resolve. Every self-hosted endpoint
# now goes through one normalizer, and the value can come from settings or env.
# --------------------------------------------------------------------------- #
def normalize_base_url(value: str | None) -> str:
    """Return a clean scheme://host[:port] origin, or "" if the value is unusable."""
    text = (value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if "://" not in text:
        # A bare host:port on a private network is plain HTTP; anything else is
        # assumed to be a public hostname served over TLS.
        text = ("http://" if _is_private_host(text) else "https://") + text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not _is_valid_netloc(parsed.netloc):
        return ""
    path = parsed.path.rstrip("/")
    # Tolerate someone pasting the endpoint rather than the origin.
    for suffix in ("/search", "/crawl", "/md", "/health", "/schema"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def searxng_base_url() -> str:
    return normalize_base_url(
        _setting(SEARXNG_URL_KEY) or os.environ.get("SEARXNG_BASE_URL")
    )


def crawl4ai_base_url() -> str:
    return normalize_base_url(
        _setting(CRAWL4AI_URL_KEY) or os.environ.get("CRAWL4AI_BASE_URL")
    )


def _is_valid_netloc(netloc: str) -> bool:
    """urlparse happily accepts spaces and other junk in the authority, so a typo
    like "my host" would otherwise become the plausible-looking "https://my host"
    and fail only at request time."""
    if not netloc or any(char.isspace() for char in netloc):
        return False
    host, _, port = netloc.rpartition(":")
    if not host:
        host, port = netloc, ""
    if port and not port.isdigit():
        return False
    return bool(host) and all(
        char.isalnum() or char in "-._[]" for char in host
    )


def _is_private_host(value: str) -> bool:
    host = value.split("/", 1)[0].split(":", 1)[0].lower()
    return (
        host in {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}
        or host.endswith(".internal")
        or host.endswith(".railway.internal")
        or host.startswith(("10.", "192.168.", "172."))
    )


def _setting(key: str) -> str | None:
    """Read one scraping setting straight from SQLite.

    Deliberately not via ``scrape_settings.get_scrape_settings`` — that function
    calls ``provider_availability`` to build its status block, so going through it
    here would recurse.
    """
    try:
        from .db import bootstrap

        conn = bootstrap()
        try:
            row = conn.execute(
                "SELECT value_json FROM app_settings WHERE key='scraping'"
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        value = json.loads(row["value_json"]).get(key)
        return value if isinstance(value, str) and value.strip() else None
    except Exception:  # noqa: BLE001 — settings are best-effort; env is the fallback
        return None


async def check_selfhosted_endpoints(client: httpx.AsyncClient) -> dict[str, Any]:
    """Live reachability probe for the Settings page, so a wrong base URL shows up
    as a concrete error instead of an empty result set later."""
    results: dict[str, Any] = {}

    searxng = searxng_base_url()
    if not searxng:
        results["searxng"] = {"ok": False, "url": None, "detail": "No base URL configured."}
    else:
        try:
            response = await client.get(
                f"{searxng}/search",
                params={"q": "esg", "format": "json"},
                headers=_SEARXNG_HEADERS,
                timeout=20.0,
            )
            payload = response.json() if response.status_code == 200 else {}
            count = len(payload.get("results") or []) if isinstance(payload, dict) else 0
            results["searxng"] = {
                "ok": response.status_code == 200 and count > 0,
                "url": f"{searxng}/search",
                "detail": (
                    f"{count} results"
                    if response.status_code == 200
                    else f"HTTP {response.status_code}"
                    + (
                        " — the JSON API is blocked. Set `limiter: false` and add "
                        "`json` to `search.formats` in settings.yml."
                        if response.status_code in (403, 429)
                        else ""
                    )
                ),
            }
        except Exception as exc:  # noqa: BLE001
            results["searxng"] = {
                "ok": False,
                "url": f"{searxng}/search",
                "detail": f"{type(exc).__name__}: {str(exc)[:160]}",
            }

    crawl4ai = crawl4ai_base_url()
    if not crawl4ai:
        results["crawl4ai"] = {"ok": False, "url": None, "detail": "No base URL configured."}
    else:
        # /schema exists on every release; /health only on newer ones. Try both so
        # the probe reflects reachability rather than which build is running.
        probe: dict[str, Any] | None = None
        for path in ("/schema", "/health"):
            try:
                response = await client.get(f"{crawl4ai}{path}", timeout=20.0)
                probe = {
                    "ok": response.status_code == 200,
                    "url": f"{crawl4ai}{path}",
                    "detail": (
                        "reachable"
                        if response.status_code == 200
                        else f"HTTP {response.status_code}"
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                probe = {
                    "ok": False,
                    "url": f"{crawl4ai}{path}",
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}",
                }
            if probe["ok"]:
                break
        results["crawl4ai"] = probe

    return results


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


# SearXNG's bot filter rejects requests that look automated. A private instance
# should run with `limiter: false`, but sending a browser-like Accept/UA pair also
# gets a limiter-enabled instance to answer, so both configurations work.
_SEARXNG_HEADERS = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


async def search_searxng(
    query: str,
    max_results: int,
    client: httpx.AsyncClient,
) -> list[ProviderSearchResult]:
    base_url = searxng_base_url()
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
        headers=_SEARXNG_HEADERS,
    )
    if response.status_code in (403, 429):
        raise RuntimeError(
            f"SearXNG rejected the JSON API (HTTP {response.status_code}) at "
            f"{base_url}/search. Set `limiter: false` and include `json` in "
            "`search.formats` in the instance settings.yml."
        )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"SearXNG at {base_url} returned non-JSON — `json` is probably missing "
            "from `search.formats` in settings.yml."
        ) from exc
    return _normalize_search_payload(payload, "searxng_search", max_results)


async def fetch_crawl4ai(
    url: str,
    client: httpx.AsyncClient,
) -> ProviderFetchResult:
    base_url = crawl4ai_base_url()
    if not base_url:
        raise RuntimeError(
            "Crawl4AI is not configured — set its base URL in Settings or "
            "CRAWL4AI_BASE_URL."
        )
    # /md is the flat, version-stable markdown endpoint. /crawl is the fallback for
    # builds where /md is unavailable; its config objects use the explicit
    # {"type", "params"} serialization the server deserializes on every release.
    text = ""
    resolved_url = url
    errors: list[str] = []
    try:
        response = await client.post(
            f"{base_url}/md",
            json={"url": url, "f": "fit", "c": "0"},
        )
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("markdown") or "") if isinstance(payload, dict) else ""
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/md {type(exc).__name__}: {str(exc)[:120]}")

    if not text.strip():
        try:
            response = await client.post(
                f"{base_url}/crawl",
                json={
                    "urls": [url],
                    "browser_config": {
                        "type": "BrowserConfig",
                        "params": {"headless": True, "text_mode": True},
                    },
                    "crawler_config": {
                        "type": "CrawlerRunConfig",
                        "params": {
                            "page_timeout": 60000,
                            "wait_until": "domcontentloaded",
                            "scan_full_page": False,
                        },
                    },
                },
            )
            response.raise_for_status()
            result = _crawl4ai_result(response.json())
            text = _crawl4ai_text(result)
            if isinstance(result, dict):
                resolved_url = str(result.get("url") or url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"/crawl {type(exc).__name__}: {str(exc)[:120]}")

    if not text.strip():
        raise RuntimeError(
            f"Crawl4AI at {base_url} returned no readable content"
            + (f" ({'; '.join(errors)})" if errors else ".")
        )
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
