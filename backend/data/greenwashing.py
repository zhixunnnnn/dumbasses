"""Greenwashing web-scrape — a REALITY check on each company's green claims.

The double-materiality composite already carries a deterministic "materiality gap" penalty
(rated greener than it actually runs). This adds the other half an equity investor wants: a
search of the OPEN WEB for whether the company is actually accused of greenwashing, or caught
in an ESG controversy, penalty, lawsuit or probe — i.e. whether the world thinks it does what
it claims. (It found, for example, that Sembcorp was accused of greenwashing over a coal sale.)

Source is the public Google-News RSS feed — a static XML feed, no bot wall — queried per
company for accusation terms, kept only when a strong controversy word is in the HEADLINE (not
a neutral listing or the company's own PR). Every kept hit ships its source + link, so the flag
is auditable — never a number with no receipt. Offline -> read cache; a failed fetch keeps the
existing cache rather than fabricating a zero.

    python -m backend.data.greenwashing            # (re)scrape -> backend/cache/greenwashing.json
    python -m backend.data.greenwashing --show     # print the cache, fetch nothing
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

from backend.engine import config

CACHE_FILE = config.CACHE_DIR / "greenwashing.json"
UA = "Mozilla/5.0 (compatible; ESGTerminal/1.0)"

# Unambiguous company name aliases used to scope the search (a bare "gulf"/"power" would sweep
# in unrelated stories — the whole point of the filter is to avoid those).
ALIASES = {
    "U96": "Sembcorp Industries", "TNB": "Tenaga Nasional", "YTLP": "YTL Power International",
    "EGCO": "Electricity Generating Public", "RATCH": "Ratch Group",
    "BGRIM": "B.Grimm Power", "GULF": "Gulf Development", "PGAS": "Perusahaan Gas Negara",
    "POWR": "Cikarang Listrindo", "POW": "PetroVietnam Power",
}

# A distinctive company token must ALSO appear in the headline — this is what drops the false
# positives (e.g. "Gulf" matching unrelated Gulf-of-Thailand political news). Deliberately
# strict for the ambiguous names, so a miss is a MISS, not someone else's controversy.
REQUIRE = {
    "U96": ("sembcorp",), "TNB": ("tenaga", "tnb"), "YTLP": ("ytl",),
    "EGCO": ("egco", "electricity generating"), "RATCH": ("ratch", "ratchaburi"),
    "BGRIM": ("grimm",), "GULF": ("gulf development", "gulf energy"),
    "PGAS": ("pgn", "perusahaan gas", "gas negara"), "POWR": ("cikarang",),
    "POW": ("petrovietnam", "pv power", "petro vietnam"),
}

# A strong controversy word must appear in the HEADLINE for a hit to count.
CONTRO = ("greenwash", "accus", "mislead", "controvers", "penalt", "fined", "lawsuit", "sued",
          "probe", "investigat", "criticis", "criticiz", "scandal", "violation", "breach",
          "backlash", "allegation", "vote against", "dispute", "arbitration", "scrutiny",
          "watchdog", "boycott", "protest", "pollut", "bribe", "corrupt", "coal expansion")
# Titles that are obviously neutral listings or the company's own PR — never a controversy.
NEUTRAL = ("stock price", "share price", "annual report", "sustainability report", "wikipedia",
           "investor relations", "awarded", "wins award", "announces", "completes", "to build",
           "signs", "partnership", "expands", "quarterly results", "dividend")


def _feed_url(alias: str) -> str:
    q = (f'"{alias}" (greenwashing OR "ESG controversy" OR accused OR penalty OR lawsuit '
         f'OR probe OR investigation OR pollution OR "vote against")')
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def _fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception:
        return None


def _hits(xml: str, require: tuple[str, ...]) -> list[dict]:
    seen, out = set(), []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        tm = re.search(r"<title>(.*?)</title>", item, re.S)
        lm = re.search(r"<link>(.*?)</link>", item, re.S)
        if not tm:
            continue
        raw = html.unescape(tm.group(1)).strip()
        low = raw.lower()
        if len(raw) < 25 or any(nw in low for nw in NEUTRAL):
            continue
        if require and not any(tok in low for tok in require):
            continue     # not actually about this company -> drop the false positive
        if not any(w in low for w in CONTRO):
            continue
        key = re.sub(r"\W+", "", low)[:80]
        if key in seen:
            continue
        seen.add(key)
        # Google News titles are "Headline - Source"
        headline, _, source = raw.rpartition(" - ")
        out.append({"title": (headline or raw)[:180], "source": source[:60],
                    "url": (html.unescape(lm.group(1)).strip() if lm else "")})
    return out[:6]


def refresh(offline: bool = False) -> dict:
    if offline:
        return cached()
    companies: dict[str, dict] = {}
    ok = False
    for cid, alias in ALIASES.items():
        xml = _fetch(_feed_url(alias))
        hits = _hits(xml, REQUIRE.get(cid, ())) if xml else []
        if xml is not None:
            ok = True
        companies[cid] = {"controversy_count": len(hits), "headlines": hits, "query_name": alias}
        print(f"  {cid:6} {len(hits)} controversy headline(s)"
              + (f"  e.g. {hits[0]['title'][:60]}" if hits else ""))
    if not ok:
        print("All fetches failed — keeping existing cache.")
        return cached()
    out = {"source": "Google News RSS", "companies": companies}
    CACHE_FILE.write_text(json.dumps(out, indent=1), "utf-8")
    print(f"Wrote {CACHE_FILE}")
    return out


def cached() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def cached_greenwashing_for(cid: str) -> dict:
    """{'controversy_count': int, 'headlines': [{title, source, url}]} — empty when unscraped."""
    rec = (cached().get("companies") or {}).get(cid)
    return rec or {"controversy_count": 0, "headlines": []}


if __name__ == "__main__":
    import sys

    if "--show" in sys.argv:
        print(json.dumps(cached(), indent=1)[:3000])
    else:
        refresh()
