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
    return {"source": "Bright Data SERP · web news",
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
    web = WebTools()  # uses the working Bright Data SERP/Web Unlocker zone from .env

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
    out = {"source": "Bright Data SERP · web news", "last_run": fetched_at,
           "companies": results}
    (config.OUT_DIR / "news.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(f"  -> stored {len(results)} companies in DB + wrote {config.OUT_DIR / 'news.json'}")
    return out


# ---------------------------------------------------------------------------
# ESG regulation compliance — scrape REAL proof per company×regulation via the
# Bright Data Scraping Browser (the working path on this account's zone; the
# token SERP / Web-Unlocker API is not enabled here).
#   * reg_source:   a real source link/excerpt per regime (provenance).
#   * reg_evidence: match each applicable, in-force regulation's disclosure
#     keywords against the company's REAL web-search result snippets; the
#     matching snippet + its source link become the proof. Found -> MET/PARTIAL;
#     not surfaced -> UNKNOWN (NULL -> falls back to the seed). Snippet absence
#     is NOT proof of non-compliance, so we never invent MISSING from a snippet.
# ---------------------------------------------------------------------------
_WEB_JS = """
() => {
  const out = [];
  document.querySelectorAll('li.b_algo').forEach(li => {
    const a = li.querySelector('h2 a');
    const p = li.querySelector('.b_caption p, p');
    if (a && a.href) out.push({title:(a.innerText||'').trim(), url:a.href,
                               snippet:(p?p.innerText:'').trim()});
  });
  return out.slice(0, 10);
}
"""


def _bing_web_url(query: str) -> str:
    from urllib.parse import quote
    return f"https://www.bing.com/search?q={quote(query)}"


def _resolve_bing_url(href):
    """Bing wraps result links in /ck/a redirects; decode the real destination."""
    if not href or "bing.com/ck/a" not in href:
        return href
    import base64
    from urllib.parse import parse_qs, urlparse
    u = (parse_qs(urlparse(href).query).get("u") or [""])[0]
    if u.startswith("a1"):
        try:
            b = u[2:] + "=" * (-len(u[2:]) % 4)
            return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return href
    return href


def _company_relevant(it: dict, aliases: list[str]) -> bool:
    blob = f"{it.get('title','')} {it.get('url','')} {it.get('snippet','')}".lower()
    return any(a in blob for a in aliases)


def _reg_applies(r: dict, sector: str, is_fi: bool, is_sgx: bool) -> bool:
    sectors = r.get("applies_to_sectors") or []
    if sectors:
        return sector in sectors
    if r["scope"] == "MAS-FI":
        return is_fi
    if r["scope"].startswith("SGX"):
        return is_sgx
    if r["scope"].startswith("ASEAN"):
        return True
    return True


def store_reg_source(conn, rows: list[dict], fetched_at: str) -> None:
    for r in rows:
        conn.execute("INSERT OR REPLACE INTO reg_source VALUES (?,?,?,?)",
                     (r["reg_id"], r.get("source_url"), r.get("source_excerpt"), fetched_at))
    conn.commit()


def store_reg_evidence(conn, rows: list[dict], fetched_at: str) -> None:
    for r in rows:
        conn.execute("INSERT OR REPLACE INTO reg_evidence VALUES (?,?,?,?,?,?,?,?)",
                     (r["company_id"], r["reg_id"], r.get("status"), r.get("matched"),
                      r.get("source_url"), r.get("source_excerpt"), fetched_at, r.get("source")))
    conn.commit()


def load_reg_evidence(conn) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM reg_evidence ORDER BY company_id, reg_id")]
    srcs = {r["reg_id"]: dict(r) for r in conn.execute("SELECT * FROM reg_source")}
    log = conn.execute("SELECT * FROM scrape_log WHERE source='regulations'").fetchone()
    return {"source": "Bright Data Scraping Browser · web search",
            "last_run": log["last_run"] if log else None, "evidence": rows, "reg_source": srcs}


def scrape_regulations(conn, offline: bool = False) -> dict:
    if offline:                                  # serve the stored snapshot, no network
        return load_reg_evidence(conn)

    from backend.engine import config as _cfg

    regs = _cfg.load_json("regulations.json")["regulations"]
    companies = conn.execute(
        "SELECT company_id, name, sector, country, sasb_industry FROM universe "
        "WHERE scope='demo'").fetchall()

    # 1) regulation provenance — one web search per regime -> a real source link.
    src_rows = []
    for r in regs:
        items = brightdata.browser_collect(
            "reg_source", r["reg_id"],
            _bing_web_url(f"{r['name']} {r['jurisdiction']} requirements"),
            _WEB_JS, ttl=30 * 86400, offline=offline) or []
        top = items[0] if items else None
        src_rows.append({"reg_id": r["reg_id"],
                         "source_url": _resolve_bing_url(top.get("url")) if top else None,
                         "source_excerpt": (top.get("snippet") or top.get("title")) if top else None})

    # 2) per-company proof — search the company's ESG disclosures, then match each
    #    applicable in-force regulation's keywords against the REAL result snippets.
    ev_rows = []
    for c in companies:
        cid, name, sector = c["company_id"], c["name"], c["sector"]
        is_fi = c["sasb_industry"] == "Commercial Banks"
        is_sgx = c["country"] == "Singapore"
        applicable = [r for r in regs
                      if _reg_applies(r, sector, is_fi, is_sgx)
                      and config.END_YEAR >= r["effective_year"]]
        if not applicable:
            continue
        aliases = _COMPANY_ALIASES.get(cid, [name.lower()])
        query = (f"{name} sustainability report TCFD climate scope 1 scope 2 "
                 "ISSB emissions governance")
        results = brightdata.browser_collect(
            "reg_company", cid, _bing_web_url(query), _WEB_JS,
            ttl=30 * 86400, offline=offline) or []
        pool = [it for it in results if _company_relevant(it, aliases)] or results

        comp = []
        for r in applicable:
            kws = r.get("disclosure_keywords", [])
            best, best_m = None, 0
            for it in pool:
                blob = f"{it.get('title', '')} {it.get('snippet', '')}".lower()
                m = sum(1 for k in kws if k.lower() in blob)
                if m > best_m:
                    best, best_m = it, m
            if best and best_m > 0:
                status = "MET" if best_m >= 2 else "PARTIAL"
                url = _resolve_bing_url(best.get("url"))
                excerpt = (best.get("snippet") or best.get("title") or "")[:280]
                source = "bing_web"
            else:
                status, url, excerpt, source = None, None, None, None   # UNKNOWN -> seed
            comp.append((r["reg_id"], status))
            ev_rows.append({"company_id": cid, "reg_id": r["reg_id"], "status": status,
                            "matched": best_m, "source_url": url, "source_excerpt": excerpt,
                            "source": source})
        summary = ", ".join(f"{rid}={s or 'UNKNOWN'}" for rid, s in comp)
        n_res = sum(1 for _, s in comp if s)
        print(f"  {cid:4} {name:24} results={len(results):2d} resolved={n_res}  {summary}")

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    store_reg_source(conn, src_rows, fetched_at)
    store_reg_evidence(conn, ev_rows, fetched_at)
    n_def = sum(1 for r in ev_rows if r["status"] in ("MET", "PARTIAL", "MISSING"))
    _log_scrape(conn, "regulations", "ok", n_def)
    print(f"  -> stored {len(ev_rows)} (company×reg) proofs ({n_def} resolved) + "
          f"{len(src_rows)} reg sources in DB")
    return load_reg_evidence(conn)


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
    ap.add_argument("--regulations", action="store_true")
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
    if args.regulations or args.all:
        print("Scraping ESG regulation compliance proof via Bright Data (deep)…")
        scrape_regulations(conn, offline=args.offline)
    conn.close()
    print("Done. Recompute with: python -m backend.engine.pipeline")


if __name__ == "__main__":
    main()
