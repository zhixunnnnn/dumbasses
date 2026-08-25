"""Real MSCI ESG letter ratings, scraped once and cached.

MSCI is read from each company's MarketScreener /ratings/ page, which renders the
agency's letter in its Ratings panel as "<LETTER> Ratings ESG MSCI". KnowESG was the
previous source but covers almost no ASEAN utility outside Singapore.

S&P Global is NOT scraped: no public S&P ESG score could be obtained for this panel, so
that channel is NULL by decision (see data/seed.py) rather than seeded with a number.
Sustainalytics publishes free public pages but forbids bulk scraping and JS-gates them to
enforce it, so it is not scraped here either — enter it by hand via
engine/manual_raters.py, which outranks this cache. We only have the *current* letter, so
the real value overlays the latest analysis year (END_YEAR); prior years keep the seeded
path.

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
from dataclasses import replace

from backend.engine import config

# Pinned MarketScreener quote pages, resolved by search and checked one by one so a
# company is never confused with a subsidiary. PETROVIETNAM-POWER-NHONTR, for instance, is
# Nhon Trach 2 (ticker NT2) and NOT PV Power — identity here is pinned, never fuzzy.
#
# PV Power (POW) is pinned but MarketScreener publishes no ESG MSCI letter for it, so it
# resolves to None and its MSCI channel stays N.A. That is a real absence of coverage.
_MS = "https://www.marketscreener.com/quote/stock/"
PINNED = {
    "U96":   f"{_MS}SEMBCORP-INDUSTRIES-LTD-6491134/ratings/",
    "TNB":   f"{_MS}TENAGA-NASIONAL-6491357/ratings/",
    "YTLP":  f"{_MS}YTL-POWER-INTL-6491745/ratings/",
    "EGCO":  f"{_MS}ELECTRICITY-GENERATING-6492378/ratings/",
    "RATCH": f"{_MS}RATCH-GROUP-57476342/ratings/",
    "BGRIM": f"{_MS}B-GRIMM-POWER-38626796/ratings/",
    "GULF":  f"{_MS}GULF-ENERGY-DEVELOPMENT-185691951/ratings/",
    "PGAS":  f"{_MS}PT-PERUSAHAAN-GAS-NEGARA--6496664/ratings/",
    "POWR":  f"{_MS}PT-CIKARANG-LISTRINDO-TBK-30640072/ratings/",
    "POW":   f"{_MS}PETROVIETNAM-POWER-CORPOR-55125609/ratings/",
}
_LETTER = r"(AAA|AA|A|BBB|BB|B|CCC)"
CACHE_FILE = config.CACHE_DIR / "realraters.json"
SOURCE = "MarketScreener"


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
            out.append(replace(r, msci_letter=info["msci"]))   # keep every other channel
        else:
            out.append(r)
    return out


# The badge renders as "<LETTER> Ratings ESG MSCI"; the reversed form is a fallback for
# layout changes. Both are anchored on the words "ESG MSCI" so a stray letter elsewhere on
# the page (a credit rating, a share class) cannot be mistaken for the ESG rating.
_MSCI_PATTERNS = (
    re.compile(r"\b" + _LETTER + r"\s+Ratings\s+ESG\s*MSCI", re.I),
    re.compile(r"ESG\s*MSCI\s+" + _LETTER + r"\b", re.I),
)


async def _fetch_one(web, cid: str, url: str, ticker: str, attempts: int = 3) -> tuple[str, dict | None]:
    code = ticker.split(".")[0]                      # 5347.KL -> 5347
    # Wrong-company guard: the page must name the ticker code or the exchange symbol.
    guard = re.compile(re.escape(code), re.I)
    # Bright Data fetches are flaky; retry a few times before giving up.
    for _ in range(attempts):
        try:
            res = await web.fetch_url(url, max_chars=60000)
            text = re.sub(r"[ \t]+", " ", res.get("text") or "")
        except Exception:
            continue
        if not text:
            continue
        if not guard.search(text):          # wrong-company guard
            continue
        for pat in _MSCI_PATTERNS:
            m = pat.search(text)
            if m:
                return cid, {"msci": m.group(1).upper(), "url": url, "source": SOURCE}
        return cid, None                    # page loaded and simply carries no ESG MSCI
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
