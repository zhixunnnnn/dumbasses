"""REAL company fundamentals from Yahoo Finance quoteSummary — the CGS-investor finance view.

Ported from the smartass app's scraper: it powers a MarketScreener-style panel (valuation /
financials / per-share & dividend / analyst ratings). Yahoo gates quoteSummary behind a
crumb+cookie, so we mint one first — no key, no BrightData. Tickers come from the engine's
own company table (comp.ticker is the Yahoo symbol), so the roster stays a single source of
truth. Writes backend/cache/fundamentals.json; a company Yahoo cannot return is cached as
null and renders N.A. — never fabricated.

    python -m backend.data.fundamentals            # (re)build the cache from Yahoo
    python -m backend.data.fundamentals --show     # print the cache, fetch nothing
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from backend.engine import config

CACHE_FILE = config.CACHE_DIR / "fundamentals.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
MODULES = ("assetProfile,summaryDetail,defaultKeyStatistics,financialData,"
           "price,recommendationTrend")


def _session() -> tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    try:
        s.get("https://fc.yahoo.com", timeout=15)
    except requests.RequestException:
        pass
    crumb = s.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=15).text.strip()
    return s, crumb


def _raw(v):
    return v.get("raw") if isinstance(v, dict) else v


def _fmt(v):
    return v.get("fmt") if isinstance(v, dict) else v


def fetch_one(s: requests.Session, crumb: str, symbol: str) -> dict | None:
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
           f"?modules={MODULES}&crumb={crumb}")
    try:
        r = s.get(url, timeout=25)
        res = (json.loads(r.text).get("quoteSummary") or {}).get("result") or []
        return res[0] if res else None
    except Exception:
        return None


def parse(r: dict) -> dict:
    ap = r.get("assetProfile") or {}
    pr = r.get("price") or {}
    sd = r.get("summaryDetail") or {}
    ks = r.get("defaultKeyStatistics") or {}
    fd = r.get("financialData") or {}
    rt = (r.get("recommendationTrend") or {}).get("trend") or []
    latest = rt[0] if rt else {}
    officers = ap.get("companyOfficers") or []
    ceo = next((o.get("name") for o in officers
                if "CEO" in (o.get("title") or "") or "Chief Executive" in (o.get("title") or "")), None)
    if not ceo and officers:
        ceo = officers[0].get("name")

    return {
        "profile": {
            "name": pr.get("longName") or pr.get("shortName"),
            "sector": ap.get("sector"), "industry": ap.get("industry"),
            "employees": ap.get("fullTimeEmployees"), "summary": ap.get("longBusinessSummary"),
            "website": ap.get("website"), "city": ap.get("city"), "country": ap.get("country"),
            "ceo": ceo, "exchange": pr.get("exchangeName"),
        },
        "financials": {
            "currency": pr.get("currency"),
            "market_cap": _raw(pr.get("marketCap")), "market_cap_fmt": _fmt(pr.get("marketCap")),
            "enterprise_value": _raw(ks.get("enterpriseValue")),
            "revenue": _raw(fd.get("totalRevenue")), "revenue_fmt": _fmt(fd.get("totalRevenue")),
            "ebitda": _raw(fd.get("ebitda")), "gross_margin": _raw(fd.get("grossMargins")),
            "operating_margin": _raw(fd.get("operatingMargins")),
            "profit_margin": _raw(fd.get("profitMargins")), "roe": _raw(fd.get("returnOnEquity")),
            "roa": _raw(fd.get("returnOnAssets")), "revenue_growth": _raw(fd.get("revenueGrowth")),
            "debt_to_equity": _raw(fd.get("debtToEquity")),
            "free_cashflow": _raw(fd.get("freeCashflow")), "current_ratio": _raw(fd.get("currentRatio")),
        },
        "valuation": {
            "trailing_pe": _raw(sd.get("trailingPE")), "forward_pe": _raw(ks.get("forwardPE")),
            "price_to_book": _raw(ks.get("priceToBook")), "peg": _raw(ks.get("pegRatio")),
            "ev_to_ebitda": _raw(ks.get("enterpriseToEbitda")),
            "eps_trailing": _raw(ks.get("trailingEps")), "book_value": _raw(ks.get("bookValue")),
            "beta": _raw(sd.get("beta")), "dividend_yield": _raw(sd.get("dividendYield")),
            "dividend_rate": _raw(sd.get("dividendRate")), "payout_ratio": _raw(sd.get("payoutRatio")),
            "fifty_two_high": _raw(sd.get("fiftyTwoWeekHigh")),
            "fifty_two_low": _raw(sd.get("fiftyTwoWeekLow")),
        },
        "ratings": {
            "recommendation": fd.get("recommendationKey"),
            "recommendation_mean": _raw(fd.get("recommendationMean")),
            "n_analysts": _raw(fd.get("numberOfAnalystOpinions")),
            "target_mean": _raw(fd.get("targetMeanPrice")), "target_high": _raw(fd.get("targetHighPrice")),
            "target_low": _raw(fd.get("targetLowPrice")),
            "current_price": _raw(fd.get("currentPrice")) or _raw(pr.get("regularMarketPrice")),
            "distribution": {
                "strongBuy": latest.get("strongBuy"), "buy": latest.get("buy"),
                "hold": latest.get("hold"), "sell": latest.get("sell"),
                "strongSell": latest.get("strongSell"),
            } if latest else None,
        },
    }


def run() -> dict:
    from backend.engine import ingest

    ds = ingest.load()
    s, crumb = _session()
    out = {"meta": {"generated": datetime.now(timezone.utc).isoformat(),
                    "source": "Yahoo Finance quoteSummary", "is_real": True}, "companies": {}}
    n_ok = 0
    for cid in ds.demo_ids():
        comp = ds.company(cid)
        r = fetch_one(s, crumb, comp.ticker)
        if r:
            out["companies"][cid] = parse(r)
            n_ok += 1
            p = out["companies"][cid]
            print(f"  {cid:6} {comp.ticker:10} mktcap={p['financials']['market_cap_fmt'] or '-':>9} "
                  f"P/E={p['valuation']['trailing_pe'] or '-'} "
                  f"reco={p['ratings']['recommendation'] or '-'}")
        else:
            out["companies"][cid] = None
            print(f"  {cid:6} {comp.ticker:10} FAILED")
    out["meta"]["is_real"] = n_ok > 0
    if n_ok == 0:
        print("Yahoo returned nothing for any ticker — keeping existing cache.")
        return cached()
    CACHE_FILE.write_text(json.dumps(out, indent=1), "utf-8")
    print(f"\nWrote {n_ok}/{len(ds.demo_ids())} companies to {CACHE_FILE}")
    return out


def cached() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def fundamentals_for(cid: str) -> dict | None:
    return (cached().get("companies") or {}).get(cid)


if __name__ == "__main__":
    import sys

    if "--show" in sys.argv:
        print(json.dumps(cached(), indent=1)[:3000])
    else:
        run()
