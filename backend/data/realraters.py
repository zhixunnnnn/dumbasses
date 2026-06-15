"""Real MSCI ESG letter ratings, scraped once and cached.

Only MSCI is reliably available from a public source (the KnowESG aggregator, which
embeds the SGX ticker + "MSCI: <letter>" in each company page). Sustainalytics and
S&P scores are gated / JS-rendered and are NOT scraped — those stay seeded and are
labelled "illustrative" in the UI. We only have the *current* letter, so the real
value overlays the latest analysis year (END_YEAR); prior years keep the seeded path.

    python -m backend.data.realraters          # (re)build the cache

The result is written to cache/realraters.json and overlaid at ingest time
(ingest.load -> realraters.overlay). One-time + cached + parallel; falls back to the
existing cache, then to seeded data, when no credentials are present.
"""
from __future__ import annotations

import asyncio
import json
import os
import re

from backend.engine import config

# Pinned, ticker-validated KnowESG pages (the 7 SGX names KnowESG actually covers).
# Sembcorp (U96), City Developments (C09) and Singtel (Z74) are not on KnowESG ->
# they keep their seeded MSCI letter.
PINNED = {
    "BN4": "https://knowesg.com/esg-ratings/keppel-corporation-ltd",
    "F34": "https://knowesg.com/esg-ratings/wilmar-international-ltd",
    "D05": "https://knowesg.com/esg-ratings/dbs",
    "U11": "https://knowesg.com/esg-ratings/united-overseas-bank-ltd",
    "9CI": "https://knowesg.com/esg-ratings/capitaland-investment-ltd",
    "C6L": "https://knowesg.com/esg-ratings/singapore-airlines",
    "O39": "https://knowesg.com/esg-ratings/ocbc-bank",
}
_LETTER = r"(AAA|AA|A|BBB|BB|B|CCC)"
CACHE_FILE = config.CACHE_DIR / "realraters.json"
SOURCE = "KnowESG"


def cached_real_raters() -> dict:
    """{cid: {"msci": "A", "url": ..., "source": ...}} from disk, or {} if none."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def overlay(raters: list, ticker_of) -> list:
    """Replace the END_YEAR MSCI letter with the cached real value where we have one.
    `raters` is a list of RaterRow; `ticker_of(cid)` returns the company's ticker.
    Returns a new list (seeded rows untouched when no real value exists)."""
    real = cached_real_raters()
    if not real:
        return raters
    out = []
    for r in raters:
        info = real.get(r.company_id)
        if info and info.get("msci") and r.year == config.END_YEAR:
            out.append(r.__class__(r.company_id, r.year, info["msci"],
                                   r.sustainalytics_risk, r.sp_global))
        else:
            out.append(r)
    return out


async def _fetch_one(web, cid: str, url: str, ticker: str, attempts: int = 3) -> tuple[str, dict | None]:
    code = ticker.split(".")[0]                      # F34.SI -> F34
    # KnowESG is inconsistent: some pages show "(F34)", others "(C6L.SI)" — accept both.
    guard = re.compile(r"\(" + re.escape(code) + r"(\.SI)?\)")
    # Bright Data fetches are flaky; retry a few times before giving up.
    for _ in range(attempts):
        try:
            res = await web.fetch_url(url, max_chars=600)
            head = re.sub(r"\s+", " ", (res.get("text") or res.get("content") or ""))[:500]
        except Exception:
            continue
        if not guard.search(head):          # wrong-company guard (e.g. Citigroup vs City Dev)
            continue
        m = re.search(r"MSCI:?\s*" + _LETTER, head)
        if m:
            return cid, {"msci": m.group(1), "url": url, "source": SOURCE}
    return cid, None


def build_real_raters(ds=None) -> dict:
    """Fetch all pinned pages in parallel, validate by ticker, cache MSCI letters."""
    from backend.app.agent import WebTools, load_env
    from backend.engine import ingest

    load_env()
    if not (os.environ.get("BRIGHTDATA_API_KEY") or os.environ.get("BRIGHTDATA_TOKEN")):
        print("No Bright Data credentials — keeping existing realraters cache / seeded MSCI.")
        return cached_real_raters()

    ds = ds or ingest.load()
    web = WebTools()

    async def run_all():
        tasks = [_fetch_one(web, cid, url, ds.company(cid).ticker) for cid, url in PINNED.items()]
        return await asyncio.gather(*tasks)

    found = {cid: info for cid, info in asyncio.run(run_all()) if info}
    if found:                              # never clobber a good cache with an empty scrape
        merged = {**cached_real_raters(), **found}
        CACHE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
    return found


def main() -> None:
    found = build_real_raters()
    print(f"Real MSCI cached for {len(found)} companies:")
    for cid, info in sorted(found.items()):
        print(f"  {cid:4} {info['msci']:4} {info['url']}")
    print(f"Cache -> {CACHE_FILE}")
    print("Rebuild the dashboard JSON:  python -m backend.engine.pipeline --offline")


if __name__ == "__main__":
    main()
