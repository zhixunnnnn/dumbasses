"""Live data acquisition via Bright Data → SQLite (overwrites the seed tables it touches).

Every fetch goes through `brightdata.fetch_or_cache` (cache + STALE fallback). Run:

    python -m backend.data.scrape --check           # verify credentials with one request
    python -m backend.data.scrape --prices          # real weekly OHLC for the demo names + STI
    python -m backend.data.scrape --news            # controversy/news signals (SERP)
    python -m backend.data.scrape --all             # everything available
    python -m backend.data.scrape --all --offline   # rebuild from the Bright Data cache only

After scraping, recompute the dashboard:  python -m backend.engine.pipeline

NOTE: with REAL prices the synthetic "flat-price" hero may no longer flag — that is the
honest outcome. `python -m backend.data.seed` always restores the deterministic demo story.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from io import StringIO
import json

from backend.engine import brightdata, config
from backend.engine.db import bootstrap

YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1wk&period1={p1}&period2={p2}"
MW_DOWNLOAD = (
    "https://www.marketwatch.com/investing/stock/{sym}/downloaddatapartial?"
    "startdate=01/01/{start}%2000:00:00&enddate=12/31/{end}%2023:59:59"
    "&daterange=custom&frequency=p7d&csvdownload=true&downloadpartial=false"
    "&newdates=false&countrycode=sg"
)


def _demo_tickers(conn) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT company_id, ticker FROM universe WHERE scope='demo'").fetchall()
    return [(r["company_id"], r["ticker"]) for r in rows] + [(config.STI_ID, "^STI")]


def _float_cell(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip().strip('"')
    if not cleaned or cleaned == "-":
        return None
    return float(cleaned)


def _int_cell(value: str | None) -> int | None:
    parsed = _float_cell(value)
    return int(parsed) if parsed is not None else None


def _provider_error(body: str) -> bool:
    text = body.lstrip()[:240].lower()
    return text.startswith("request failed") or "bad_endpoint" in text


def _parse_yahoo_prices(body: str) -> list[tuple[str, float, float, float, float, int | None]]:
    if _provider_error(body):
        raise ValueError("Bright Data provider returned an endpoint error")
    res = json.loads(body)["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    vols = q.get("volume") or [None] * len(ts)
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        d = dt.datetime.fromtimestamp(t, dt.UTC).date().isoformat()
        rows.append((d, round(o, 3), round(h, 3), round(l, 3), round(c, 3), vols[i]))
    return rows


def _fetch_native_yahoo(url: str) -> str | None:
    import requests

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                )
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.text
    except Exception:
        return None


def _marketwatch_symbol(sym: str) -> str | None:
    if sym.startswith("^"):
        return None
    base = sym.split(".", 1)[0].strip().lower()
    return base or None


def _parse_marketwatch_prices(body: str) -> list[tuple[str, float, float, float, float, int | None]]:
    if _provider_error(body):
        raise ValueError("Bright Data provider returned an endpoint error")
    rows = []
    reader = csv.DictReader(StringIO(body))
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("MarketWatch CSV did not include OHLCV columns")
    for item in reader:
        o = _float_cell(item.get("Open"))
        h = _float_cell(item.get("High"))
        l = _float_cell(item.get("Low"))
        c = _float_cell(item.get("Close"))
        if None in (o, h, l, c):
            continue
        date = dt.datetime.strptime(item["Date"], "%m/%d/%Y").date().isoformat()
        rows.append((date, round(o, 3), round(h, 3), round(l, 3), round(c, 3), _int_cell(item.get("Volume"))))
    rows.sort(key=lambda row: row[0])
    return rows


def _insert_price_rows(conn, cid: str, rows: list[tuple[str, float, float, float, float, int | None]]) -> None:
    conn.execute("DELETE FROM prices WHERE company_id=?", (cid,))
    conn.executemany(
        "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
        [(cid, *row) for row in rows],
    )


def scrape_prices(conn, offline: bool = False) -> int:
    p1 = int(dt.datetime(config.START_YEAR, 1, 1).timestamp())
    p2 = int(dt.datetime(config.END_YEAR, 12, 31).timestamp())
    total = 0
    for cid, sym in _demo_tickers(conn):
        url = YF_CHART.format(sym=sym.replace("^", "%5E"), p1=p1, p2=p2)
        body = brightdata.fetch_or_cache("yahoo_prices", sym, url, ttl=7 * 86400, offline=offline)
        rows: list[tuple[str, float, float, float, float, int | None]] = []
        source = "Yahoo"
        errors = []
        try:
            if body:
                rows = _parse_yahoo_prices(body)
            else:
                errors.append("Yahoo returned no body")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Yahoo {type(exc).__name__}: {exc}")

        if not rows and not offline:
            try:
                native_body = _fetch_native_yahoo(url)
                if native_body:
                    rows = _parse_yahoo_prices(native_body)
                    source = "Yahoo native fallback"
                else:
                    errors.append("Yahoo native fallback returned no body")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Yahoo native fallback {type(exc).__name__}: {exc}")

        if not rows:
            mw_sym = _marketwatch_symbol(sym)
            if mw_sym:
                mw_url = MW_DOWNLOAD.format(sym=mw_sym, start=config.START_YEAR, end=config.END_YEAR)
                mw_body = brightdata.fetch_or_cache(
                    "marketwatch_prices",
                    sym,
                    mw_url,
                    ttl=7 * 86400,
                    offline=offline,
                )
                try:
                    if mw_body:
                        rows = _parse_marketwatch_prices(mw_body)
                        source = "MarketWatch CSV"
                    else:
                        errors.append("MarketWatch returned no body")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"MarketWatch {type(exc).__name__}: {exc}")

        if rows:
            _insert_price_rows(conn, cid, rows)
            total += len(rows)
            print(f"  {sym:8} {len(rows):4d} weekly bars ({source})")
        else:
            print(f"  {sym:8} no valid price rows ({'; '.join(errors)})")
    conn.commit()
    return total


_NEWS_JS = """
() => {
  // ONLY real Bing News card titles — avoids grabbing 'no results' placeholder text.
  const out = [];
  document.querySelectorAll('a.title').forEach(a => {
    const t=(a.innerText||'').trim();
    if(t && t.length>15) out.push({title:t, url:a.href});
  });
  return out.slice(0, 20);
}
"""

_NO_RESULT = ["didn't find", "did not find", "no se han encontrado", "no results",
              "check your spelling", "n'a trouvé aucun"]

# We keep ONLY company-specific ESG news and stock/market news. Everything else
# (generic ESG think-pieces, unrelated articles that merely matched the keyword) is dropped.
_COMPANY_ALIASES = {
    "U96": ["sembcorp"], "BN4": ["keppel"], "F34": ["wilmar"],
    "C6L": ["singapore airlines", "sia "], "D05": ["dbs"], "O39": ["ocbc"],
    "U11": ["uob", "united overseas bank"], "9CI": ["capitaland"],
    "C09": ["city developments", "cdl"], "Z74": ["singtel", "singapore telecom"],
}

_ESG_KW = ["esg", "sustainab", "emission", "carbon", "climate", "governance", "renewable",
           "net zero", "net-zero", "green", "decarbon", "diversity", "controvers",
           "deforestation", "pollution", "transition", "scope 1", "scope 2", "tcfd"]
_STOCK_KW = ["stock", "shares", "shareholder", "share price", "earnings", "results", "profit",
             "revenue", "dividend", "target price", "upgrade", "downgrade", "analyst", "guidance",
             "quarter", "q1", "q2", "q3", "q4", "outperform", "underperform", "rating",
             "market cap", "buyback", "valuation", "deal", "stake", "acquisition", "merger",
             "listed", "sgx:", "ipo"]

_CONTROVERSY = ["lawsuit", "fine", "fined", "probe", "scandal", "deforestation", "breach",
                "penalt", "violation", "pollution", "spill", "abuse", "greenwash", "sued",
                "allegation", "investigat", "boycott", "haze", "downgrade", "plunge", "slump"]
_POSITIVE = ["renewable", "net zero", "net-zero", "decarbon", "green bond", "award", "solar",
             "wind", "recycl", "verified", "upgrade", "outperform", "record", "wins", "win ",
             "profit", "growth"]


def _log_scrape(conn, source: str, status: str, rows: int) -> None:
    conn.execute("INSERT OR REPLACE INTO scrape_log VALUES (?,?,?,?)",
                 (source, dt.datetime.utcnow().isoformat(timespec="seconds"), status, rows))
    conn.commit()


def store_news(conn, results: list[dict], fetched_at: str) -> None:
    """Persist a news snapshot in the DB so it survives restarts and isn't re-scraped."""
    for r in results:
        cid = r["company_id"]
        conn.execute("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?)",
                     (cid, fetched_at, r["n_items"], r["controversy"], r["positive"], r["sentiment"]))
        conn.execute("DELETE FROM news_headlines WHERE company_id=?", (cid,))
        for h in r["headlines"]:
            conn.execute("INSERT INTO news_headlines VALUES (?,?,?,?,?)",
                         (cid, fetched_at, h["title"], h.get("url"), h["label"]))
    conn.commit()


def load_news(conn) -> dict:
    """Read the latest news snapshot from the DB (used by /api/news)."""
    companies = []
    for n in conn.execute(
            "SELECT nw.*, u.name AS cname, u.sector AS sector, u.ticker AS ticker FROM news nw "
            "LEFT JOIN universe u ON u.company_id = nw.company_id ORDER BY nw.company_id"):
        cid = n["company_id"]
        heads = [{"title": h["title"], "url": h["url"], "label": h["label"]}
                 for h in conn.execute(
                     "SELECT * FROM news_headlines WHERE company_id=?", (cid,))]
        companies.append({"company_id": cid, "name": n["cname"] or cid,
                          "sector": n["sector"], "ticker": n["ticker"], "n_items": n["n_items"],
                          "controversy": n["controversy"], "positive": n["positive"],
                          "sentiment": n["sentiment"], "fetched_at": n["fetched_at"],
                          "headlines": heads})
    log = conn.execute("SELECT * FROM scrape_log WHERE source='news'").fetchone()
    return {"source": "Bright Data Request API - Bing News",
            "last_run": log["last_run"] if log else None, "companies": companies}


def _relevant_label(title: str, cid: str):
    """Keep ONLY headlines that (a) actually name the company and (b) are ESG- or
    stock-topical. Returns the label, or None to DROP (generic/irrelevant noise)."""
    t = title.lower()
    if any(x in t for x in _NO_RESULT):
        return None                                   # Bing 'no results' placeholder -> drop
    if not any(a in t for a in _COMPANY_ALIASES.get(cid, [])):
        return None                                   # not about this company -> drop
    is_esg = any(k in t for k in _ESG_KW)
    is_stock = any(k in t for k in _STOCK_KW)
    if not (is_esg or is_stock):
        return None                                   # not ESG/stock related -> drop
    if any(k in t for k in _CONTROVERSY):
        return "controversy"
    if is_esg and any(k in t for k in _POSITIVE):
        return "positive"
    if is_stock:
        return "stock"
    return "neutral"


def _bing_url(query: str) -> str:
    from urllib.parse import quote
    return f"https://www.bing.com/news/search?q={quote(query)}"


def scrape_news(conn, offline: bool = False) -> dict:
    # Offline = don't hit the network; just serve whatever snapshot is already stored.
    if offline:
        return load_news(conn)

    import asyncio

    from backend.app.agent import WebTools

    rows = conn.execute("SELECT company_id, name FROM universe WHERE scope='demo'").fetchall()
    web = WebTools()  # uses Bright Data Request/Web Unlocker API when keys are configured.

    async def collect_one(cid: str, name: str) -> dict:
        # Broad queries for recall; the relevance + topical filter keeps only
        # company-named ESG / stock headlines.
        queries = [
            f"{name} sustainability ESG news",
            f"{name} stock earnings results news",
        ]
        kept, seen = [], set()
        for q in queries:
            try:
                res = await web.search(q, max_results=10)
            except Exception:
                continue
            for it in res.get("results", []):
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                # classify on title + snippet for recall; store the title as the headline
                label = _relevant_label(f"{title} {it.get('snippet') or ''}", cid)
                if not label:
                    continue
                key = title.lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                kept.append({"title": title, "url": it.get("url"), "label": label})
        ncon = sum(1 for c in kept if c["label"] == "controversy")
        npos = sum(1 for c in kept if c["label"] == "positive")
        nstk = sum(1 for c in kept if c["label"] == "stock")
        print(f"  {cid:4} {name:24} kept={len(kept):2d} (esg+/-={npos}/{ncon}, stock={nstk})")
        return {"company_id": cid, "name": name, "n_items": len(kept),
                "controversy": ncon, "positive": npos, "sentiment": npos - ncon,
                "headlines": kept[:8]}

    async def collect_all() -> list[dict]:
        return await asyncio.gather(
            *[collect_one(r["company_id"], r["name"]) for r in rows]
        )

    results = asyncio.run(collect_all())
    fetched_at = dt.datetime.utcnow().isoformat(timespec="seconds")
    store_news(conn, results, fetched_at)                       # persist in the DB (durable)
    _log_scrape(conn, "news", "ok", sum(r["n_items"] for r in results))
    out = {"source": "Bright Data Request API - Bing News", "last_run": fetched_at,
           "companies": results}
    (config.OUT_DIR / "news.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(f"  -> stored {len(results)} companies in DB + wrote {config.OUT_DIR / 'news.json'}")
    return out


def check() -> bool:
    if not brightdata.available():
        print("No Bright Data credentials found in backend/.env "
              "(set BRIGHTDATA_API_KEY + BRIGHTDATA_ZONE).")
        return False
    body = brightdata.fetch_or_cache("check", "httpbin", "https://geo.brightdata.com/", ttl=0)
    ok = bool(body)
    print("Bright Data credentials OK." if ok else "Bright Data request failed — check token/zone.")
    if body:
        print(f"  sample response: {body[:160].strip()}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--prices", action="store_true")
    ap.add_argument("--news", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    if args.check:
        check()
        return

    conn = bootstrap()
    if args.prices or args.all:
        print("Scraping prices via Bright Data…")
        n = scrape_prices(conn, offline=args.offline)
        print(f"  -> {n} price rows written")
    if args.news or args.all:
        print("Scraping live news/controversy via Bright Data Request API...")
        scrape_news(conn, offline=args.offline)
    conn.close()
    print("Done. Recompute with: python -m backend.engine.pipeline")


if __name__ == "__main__":
    main()
