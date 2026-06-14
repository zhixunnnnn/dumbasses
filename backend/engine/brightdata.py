"""Bright Data fetch boundary with mandatory cache + STALE fallback (build-spec §3.2).

Supports two credential modes (set in backend/.env — never committed):
  * API token  : BRIGHTDATA_API_KEY=<bearer token>  + BRIGHTDATA_ZONE=<zone name>
                 -> POST https://api.brightdata.com/request {zone,url,format}
  * Proxy      : BRIGHTDATA_PROXY=http://brd-customer-..-zone-..:<pw>@brd.superproxy.io:33335

Every live fetch goes through `fetch_or_cache`. On any failure we fall back to the
cached copy and log STALE — the pipeline never crashes on a fetch error. The token
is read from the environment and is never logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from . import config

API_URL = "https://api.brightdata.com/request"
_DEFAULT_TTL = 24 * 3600


def _browser_wss() -> Optional[str]:
    """Build the Scraping Browser CDP endpoint (wss://user:pass@host:9222) from the proxy creds."""
    explicit = os.environ.get("BRIGHTDATA_BROWSER_WSS")
    if explicit:
        return explicit
    proxy = _proxy()
    if not proxy:
        return None
    m = re.match(r"https?://([^:]+):([^@]+)@([^:/]+)", proxy)
    if not m:
        return None
    user, pw, host = m.groups()
    return f"wss://{user}:{pw}@{host}:9222"


def browser_available() -> bool:
    return bool(_browser_wss())


def _token() -> Optional[str]:
    return os.environ.get("BRIGHTDATA_API_KEY")


def _zone() -> str:
    return os.environ.get("BRIGHTDATA_ZONE", "web_unlocker1")


def _proxy() -> Optional[str]:
    return os.environ.get("BRIGHTDATA_PROXY")


def available() -> bool:
    return bool(_token() or _proxy())


def _cache_path(source: str, key: str) -> Path:
    safe = hashlib.sha1(key.encode()).hexdigest()[:16]
    d = config.CACHE_DIR / "brightdata" / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.txt"


def _via_api(url: str, fmt: str, timeout: int) -> str:
    import requests

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={"zone": _zone(), "url": url, "format": fmt},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def _via_proxy(url: str, timeout: int) -> str:
    import requests

    resp = requests.get(url, proxies={"http": _proxy(), "https": _proxy()},
                        timeout=timeout, verify=False)
    resp.raise_for_status()
    return resp.text


def _live_fetch(url: str, fmt: str, timeout: int) -> str:
    """Try API-token mode first, then proxy mode (whichever creds exist)."""
    errors = []
    if _token():
        try:
            return _via_api(url, fmt, timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"api:{type(exc).__name__}")
    if _proxy():
        try:
            return _via_proxy(url, timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"proxy:{type(exc).__name__}")
    raise RuntimeError("Bright Data fetch failed (" + ", ".join(errors or ["no credentials"]) + ")")


def _json_cache(source: str, key: str) -> Path:
    safe = hashlib.sha1(key.encode()).hexdigest()[:16]
    d = config.CACHE_DIR / "brightdata" / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.json"


def browser_collect(source: str, key: str, url: str, extract_js: str, *,
                    ttl: int = _DEFAULT_TTL, offline: bool = False, timeout: int = 60000):
    """Render `url` in the Bright Data Scraping Browser and run `extract_js` in the page.

    Returns the JS result (JSON-serialisable), cached to disk. offline/no-creds -> cache only.
    Live failure -> STALE cache fallback. One Bright Data session per call (avoids the
    per-session domain limit).
    """
    cache = _json_cache(source, key)
    fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < ttl
    if offline or not browser_available():
        return json.loads(cache.read_text("utf-8")) if cache.exists() else None
    if fresh:
        return json.loads(cache.read_text("utf-8"))
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(_browser_wss(), timeout=90000)
            page = browser.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            data = page.evaluate(extract_js)
            browser.close()
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return data
    except Exception as exc:  # noqa: BLE001 — never crash the pipeline
        if cache.exists():
            age = int((time.time() - cache.stat().st_mtime) / 3600)
            print(f"[STALE] {source}/{key}: browser fetch failed ({type(exc).__name__}); cache ~{age}h")
            return json.loads(cache.read_text("utf-8"))
        print(f"[MISS] {source}/{key}: browser fetch failed ({type(exc).__name__}: {str(exc)[:80]})")
        return None


def fetch_or_cache(source: str, key: str, url: str, *, ttl: int = _DEFAULT_TTL,
                   fmt: str = "raw", timeout: int = 60, offline: bool = False) -> Optional[str]:
    """Return the response body for `url`, going through the cache boundary.

    offline=True (or no creds) -> cache only. Live failure -> STALE cache fallback.
    Returns None only if there is neither a live response nor a cached copy.
    """
    cache = _cache_path(source, key)
    fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < ttl

    if offline or not available():
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        return None
    if fresh:
        return cache.read_text(encoding="utf-8")

    try:
        body = _live_fetch(url, fmt, timeout)
        cache.write_text(body, encoding="utf-8")
        return body
    except Exception as exc:  # noqa: BLE001 — never crash the pipeline on a fetch error
        if cache.exists():
            age = int((time.time() - cache.stat().st_mtime) / 3600)
            print(f"[STALE] {source}/{key}: live fetch failed ({type(exc).__name__}); "
                  f"using cache aged ~{age}h")
            return cache.read_text(encoding="utf-8")
        print(f"[MISS] {source}/{key}: live fetch failed and no cache ({type(exc).__name__})")
        return None
