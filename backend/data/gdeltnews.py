"""DATED news per company-YEAR, so a model row can use the news of ITS OWN time.

The `news_headlines` table is a single snapshot (everything fetched on one day), which is
the right signal for a nowcast made today and useless for 2021: back-filling it would put
2026 knowledge into a 2021 row. GDELT's DOC 2.0 API is open, keyless and date-ranged, so
it can be asked what was published about a company DURING year t and nothing after.

The label is produced by the repo's OWN headline classifier (scrape._llm_label_headlines),
the same prompt that labels the live snapshot, so the feature means the same thing in every
row of the panel — including the current-year row, which is fetched from GDELT too rather
than from the snapshot. Sentiment is `positive - controversy`, exactly as scrape.py stores it.

Every cache entry records its provenance: the exact query, the window, and when it was
fetched. A company-year GDELT has no articles for is a MISS — never a zero.

    python -m backend.data.gdeltnews                    # all companies, 2019..CURRENT_YEAR
    python -m backend.data.gdeltnews --years 2021-2024
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.engine import config

CACHE_SUBDIR = "gdeltnews"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS = 250            # GDELT's per-call ceiling for artlist
THROTTLE_SECONDS = 5.0       # the open endpoint 429s well below its documented rate
UNLOCKER_TIMEOUT = 120.0     # seconds
MAX_HEADLINES_LABELLED = 60  # one LLM call per company-year, same prompt as scrape.py
# One direct try, then the unlocker. A company-year neither route answers is left
# uncached and picked up by the next run — waiting out a GDELT block in-process costs
# minutes per company-year and rarely clears.

# One quoted phrase per company — the form that actually appears in headlines. GDELT's
# OR-groups returned nothing for these names, so recall comes from the shortest phrase
# that is still unambiguous, and the LLM labeller drops whatever is not about the company.
QUERIES = {
    "U96": '"Sembcorp"',
    "TNB": '"Tenaga Nasional"',
    "YTLP": '"YTL Power"',
    "EGCO": '"Electricity Generating Public"',
    "RATCH": '"Ratch Group"',
    "BGRIM": '"B.Grimm Power"',
    # "Gulf" alone matches the Persian Gulf, Gulf of Mexico and several banks, so the
    # company name is never shortened here.
    "GULF": '"Gulf Development" OR "Gulf Energy Development"',
    "PGAS": '"Perusahaan Gas Negara"',
    "POWR": '"Cikarang Listrindo"',
    "POW": '"PetroVietnam Power" OR "PV Power"',
}


def cache_path_for(cid: str, year: int) -> Path:
    return config.CACHE_DIR / CACHE_SUBDIR / f"{cid}_{year}.json"


def read_cache(cid: str, year: int) -> dict | None:
    path = cache_path_for(cid, year)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def sentiment_at(cid: str, year: int) -> int | None:
    """positive - controversy for THAT year, or None when the year has no fetched news.

    None is the honest answer for a missing year; callers drop the row rather than
    substituting a zero or the present-day snapshot.
    """
    cached = read_cache(cid, year)
    if not cached or cached.get("miss"):
        return None
    return int(cached.get("sentiment") or 0)


def _window(year: int) -> tuple[str, str]:
    """The calendar year, clipped at today for the year still in progress."""
    end = min(date(year, 12, 31), date.today())
    return f"{year}0101000000", end.strftime("%Y%m%d") + "235959"


async def _via_unlocker(url: str) -> Optional[str]:
    """GDELT throttles a single IP hard once a backfill gets going. The repo already has
    an unlocker for exactly this; it is the same open endpoint and the same query, just
    not from an IP GDELT has grown tired of.

    Awaited on the caller's own loop — an asyncio.run() nested inside a worker thread
    deadlocked here on Windows.
    """
    from backend.app.agent import WebTools, load_env

    load_env()
    try:
        # hard deadline: the unlocker occasionally hangs, and one stuck company-year must
        # not stall the whole backfill
        result = await asyncio.wait_for(WebTools()._fetch_html(url), UNLOCKER_TIMEOUT)
    except Exception:
        return None
    return str(result.get("html") or "") or None


def _articles(body: str) -> Optional[list[dict]]:
    try:
        return json.loads(body).get("articles") or []
    except Exception:
        # the unlocker may hand back the JSON wrapped in a viewer page
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(body[start:end + 1]).get("articles") or []
        except Exception:
            return None


def _query_url(query: str, start: str, end: str) -> str:
    params = {"query": f"{query} sourcelang:english", "mode": "artlist",
              "maxrecords": MAX_RECORDS, "sort": "hybridrel", "format": "json",
              "startdatetime": start, "enddatetime": end}
    return f"{API}?{urllib.parse.urlencode(params)}"


def _fetch_direct(url: str) -> Optional[list[dict]]:
    try:
        with urllib.request.urlopen(url, timeout=90) as fh:
            return _articles(fh.read().decode("utf-8", "replace"))
    except Exception:
        return None


async def _fetch(query: str, start: str, end: str) -> tuple[Optional[list[dict]], str]:
    """Articles, or None when neither route answered. None is NOT an empty year: a
    throttled call must not be cached as "no news happened"."""
    url = _query_url(query, start, end)
    rows = await asyncio.to_thread(_fetch_direct, url)
    if rows is not None:
        return rows, url
    body = await _via_unlocker(url)
    return (_articles(body) if body else None), url


async def _label(client, name: str, items: list[dict]) -> tuple[list[dict], str]:
    """Label with the repo's classifier; no keyword fallback here — an unlabelled
    company-year is a MISS, because a keyword guess is not the same feature."""
    from backend.data.scrape import _llm_label_headlines

    if client is None:
        return [], "none"
    labels = await _llm_label_headlines(client, name, items)
    if labels is None:
        return [], "none"
    kept = [{"title": it["title"], "url": it.get("url"), "seendate": it.get("seendate"),
             "label": labels[i]}
            for i, it in enumerate(items) if labels.get(i) and labels[i] != "irrelevant"]
    return kept, "llm"


def build(cids: list[str], years: list[int], refresh: bool = False) -> None:
    from backend.data.scrape import _news_llm_client
    from backend.engine import ingest

    ds = ingest.load()
    client = _news_llm_client()
    if client is None:
        print("No OPENROUTER_API_KEY — headline labelling is unavailable; nothing to build.")
        return

    async def run() -> None:
        for year in years:
            print(f"--- news year {year} ---")
            for cid in cids:
                if not refresh and read_cache(cid, year) is not None:
                    print(f"  {cid:4} {year} cached")
                    continue
                name = ds.company(cid).name
                start, end = _window(year)
                articles, url = await _fetch(QUERIES[cid], start, end)
                time.sleep(THROTTLE_SECONDS)
                if articles is None:
                    # the API refused, so we know nothing about this year — leave it
                    # uncached so a rerun picks it up instead of freezing in a fake MISS
                    print(f"  {cid:4} {year} API unavailable — not cached")
                    continue
                items = [{"title": a.get("title") or "", "url": a.get("url"),
                          "seendate": a.get("seendate")}
                         for a in articles if a.get("title")][:MAX_HEADLINES_LABELLED]
                kept, how = await _label(client, name, items) if items else ([], "none")
                pos = sum(1 for k in kept if k["label"] == "positive")
                con = sum(1 for k in kept if k["label"] == "controversy")
                payload = {
                    "company_id": cid, "year": year, "miss": not kept,
                    "n_articles": len(articles), "n_labelled": len(kept),
                    "positive": pos, "controversy": con, "sentiment": pos - con,
                    "headlines": kept[:12],
                    # provenance: what was asked, of whom, over which window, and when
                    "source": "GDELT DOC 2.0 (artlist)", "query": QUERIES[cid],
                    "query_url": url, "window_start": start, "window_end": end,
                    "labeller": how,
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                path = cache_path_for(cid, year)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
                print(f"  {cid:4} {year} arts={len(articles):3d} labelled={len(kept):2d} "
                      f"(+{pos}/-{con}) sentiment={pos - con}")

    asyncio.run(run())


def coverage() -> str:
    lines = []
    for cid in QUERIES:
        cells = []
        for year in range(config.START_YEAR, config.CURRENT_YEAR + 1):
            value = sentiment_at(cid, year)
            cells.append(f"{year}:{'--' if value is None else value:>3}")
        lines.append(f"  {cid:4} " + "  ".join(cells))
    return "\n".join(lines)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    refresh = "--refresh" in args
    args = [a for a in args if a != "--refresh"]
    years = list(range(config.START_YEAR, config.CURRENT_YEAR + 1))
    if "--years" in args:
        i = args.index("--years")
        spec = args[i + 1]
        years = (list(range(int(spec.split("-")[0]), int(spec.split("-")[1]) + 1))
                 if "-" in spec else [int(y) for y in spec.split(",")])
        del args[i:i + 2]
    cids = [c.upper() for c in args] or list(QUERIES)
    build(cids, years, refresh=refresh)
    print("\nSentiment (positive - controversy) by company x year:")
    print(coverage())


if __name__ == "__main__":
    main()
