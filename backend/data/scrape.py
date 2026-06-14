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
import datetime as dt
import json

from backend.engine import brightdata, config
from backend.engine.db import bootstrap

YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1wk&period1={p1}&period2={p2}"


def _demo_tickers(conn) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT company_id, ticker FROM universe WHERE scope='demo'").fetchall()
    return [(r["company_id"], r["ticker"]) for r in rows] + [(config.STI_ID, "^STI")]


def scrape_prices(conn, offline: bool = False) -> int:
    p1 = int(dt.datetime(config.START_YEAR, 1, 1).timestamp())
    p2 = int(dt.datetime(config.END_YEAR, 12, 31).timestamp())
    total = 0
    for cid, sym in _demo_tickers(conn):
        url = YF_CHART.format(sym=sym.replace("^", "%5E"), p1=p1, p2=p2)
        body = brightdata.fetch_or_cache("yahoo_prices", sym, url, ttl=7 * 86400, offline=offline)
        if not body:
            print(f"  {sym:8} no data")
            continue
        try:
            res = json.loads(body)["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            vols = q.get("volume") or [None] * len(ts)
            rows = 0
            for i, t in enumerate(ts):
                o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                if None in (o, h, l, c):
                    continue
                d = dt.datetime.utcfromtimestamp(t).date().isoformat()
                conn.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                             (cid, d, round(o, 3), round(h, 3), round(l, 3), round(c, 3), vols[i]))
                rows += 1
            total += rows
            print(f"  {sym:8} {rows:4d} weekly bars")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:8} parse failed: {type(exc).__name__}: {exc}")
    conn.commit()
    return total


_NEWS_JS = """
() => {
  const out = [];
  document.querySelectorAll('a.title').forEach(a => {
    const t=(a.innerText||'').trim(); if(t) out.push({title:t, url:a.href});
  });
  if(out.length===0){
    document.querySelectorAll('a').forEach(a=>{const t=(a.innerText||'').trim();
      if(t.length>45 && out.length<15) out.push({title:t, url:a.href});});
  }
  return out.slice(0,15);
}
"""

_CONTROVERSY = ["lawsuit", "fine", "fined", "probe", "scandal", "deforestation", "breach",
                "penalt", "violation", "pollution", "spill", "abuse", "greenwash", "sued",
                "allegation", "investigat", "boycott", "haze"]
_POSITIVE = ["renewable", "net zero", "net-zero", "decarbon", "green bond", "sustainab",
             "award", "verified", "solar", "wind", "recycl", "emission", "esg leader", "transition"]


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
            "SELECT nw.*, u.name AS cname FROM news nw "
            "LEFT JOIN universe u ON u.company_id = nw.company_id ORDER BY nw.company_id"):
        cid = n["company_id"]
        heads = [{"title": h["title"], "url": h["url"], "label": h["label"]}
                 for h in conn.execute(
                     "SELECT * FROM news_headlines WHERE company_id=?", (cid,))]
        companies.append({"company_id": cid, "name": n["cname"] or cid, "n_items": n["n_items"],
                          "controversy": n["controversy"], "positive": n["positive"],
                          "sentiment": n["sentiment"], "fetched_at": n["fetched_at"],
                          "headlines": heads})
    log = conn.execute("SELECT * FROM scrape_log WHERE source='news'").fetchone()
    return {"source": "Bright Data Scraping Browser · Bing News",
            "last_run": log["last_run"] if log else None, "companies": companies}


def _classify(title: str) -> str:
    t = title.lower()
    if any(k in t for k in _CONTROVERSY):
        return "controversy"
    if any(k in t for k in _POSITIVE):
        return "positive"
    return "neutral"


def scrape_news(conn, offline: bool = False) -> dict:
    rows = conn.execute("SELECT company_id, name FROM universe WHERE scope='demo'").fetchall()
    results = []
    for r in rows:
        cid, name = r["company_id"], r["name"]
        q = f"{name} ESG sustainability controversy".replace(" ", "%20")
        url = f"https://www.bing.com/news/search?q={q}"
        items = brightdata.browser_collect("bing_news", cid, url, _NEWS_JS,
                                           ttl=7 * 86400, offline=offline) or []
        cls = [{"title": i["title"], "url": i.get("url"), "label": _classify(i["title"])} for i in items]
        ncon = sum(1 for c in cls if c["label"] == "controversy")
        npos = sum(1 for c in cls if c["label"] == "positive")
        sentiment = (npos - ncon)
        results.append({"company_id": cid, "name": name, "n_items": len(cls),
                        "controversy": ncon, "positive": npos, "sentiment": sentiment,
                        "headlines": cls[:6]})
        sample = next((c["title"] for c in cls if c["label"] == "controversy"),
                      cls[0]["title"] if cls else "—")
        print(f"  {cid:4} {name:24} items={len(cls):2d} contro={ncon} pos={npos}  e.g. “{sample[:60]}”")
    fetched_at = dt.datetime.utcnow().isoformat(timespec="seconds")
    store_news(conn, results, fetched_at)                       # persist in the DB (durable)
    _log_scrape(conn, "news", "ok", sum(r["n_items"] for r in results))
    out = {"source": "Bright Data Scraping Browser · Bing News", "last_run": fetched_at,
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
        print("Scraping live news/controversy via Bright Data Scraping Browser…")
        scrape_news(conn, offline=args.offline)
    conn.close()
    print("Done. Recompute with: python -m backend.engine.pipeline")


if __name__ == "__main__":
    main()
