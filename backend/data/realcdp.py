"""REAL CDP climate scores, read from CDP's own public scores table.

TERMS — READ BEFORE EXTENDING THIS MODULE
    CDP's published terms for the public scores state, verbatim:

        "CDP Scores must not, without prior written consent from CDP, be used for
         anything other than internal, non-commercial use."

    We rely on the internal, non-commercial carve-out: this project is a prototype in
    development, the scores are used internally to sanity-check a rater channel, and they
    are not redistributed. Shipping commercially, or republishing these scores publicly,
    requires PRIOR WRITTEN CONSENT FROM CDP. That decision has not been taken; if it is,
    this module and anything that surfaces its output must be revisited first.

WHAT THIS FETCHES
    cdp.net/en/data/scores renders its table through a Flourish embed, and the whole
    dataset ships inside that page as a `_Flourish_data` JSON blob. We read that blob
    directly. Note this is raw HTTP rather than the house WebTools helper: WebTools
    extracts readable TEXT, which discards the <script> payload the data lives in.

    Scores are encoded as icon filenames ("Climate-B-minus-Icon-grey-text.svg" -> "B-"),
    so the parser maps the filename, never the pixel.

"DID NOT DISCLOSE" IS NOT A SCORE
    The table's non-score cells — "Did not disclose", "Not Scored", "See disclosing
    organisation", blank — mean the company did not respond, or was not assessed. That is
    a disclosure FACT, not a bad grade. Those rows are cached with `status` set and
    `value_raw` None, and they never reach a rater channel, a percentile or an average.
    A company that declined to answer must not be ranked below one that scored a D-.

COMPANY IDENTITY IS PINNED, NOT FUZZY-MATCHED
    The table lists sibling entities whose scores differ — "DBS Bank Ltd." did not
    disclose while "DBS Group Holdings" scored B; "Keppel Ltd." did not disclose while
    several Keppel trusts are listed separately. Fuzzy matching would silently pick the
    wrong legal entity, so each company's row is pinned by exact name + country.

    python -m backend.data.realcdp            # (re)build the cache
    python -m backend.data.realcdp --show     # print the cache, fetch nothing
"""
from __future__ import annotations

import json
import re
import time
import sys
import urllib.request
from datetime import datetime, timezone

from backend.engine import config

# The Flourish visualisation behind cdp.net/en/data/scores.
SCORES_URL = "https://flo.uri.sh/visualisation/28119771/embed"
HUMAN_URL = "https://www.cdp.net/en/data/scores"      # the citable page for the UI
CACHE_FILE = config.CACHE_DIR / "realcdp.json"
SOURCE = "CDP public scores table"
THEME_COLUMN = "Climate"        # CDP scores Climate, Forests and Water separately; the
                                # rater channel is climate only, matching realratings.py
FETCH_TIMEOUT = 120
_MIN_HTML_BYTES = 3_000_000   # the real embed page is ~4.2MB; anything less is a truncated read
USER_AGENT = "Mozilla/5.0 (compatible; polyfintech-esg-prototype/1.0)"

# Exact table name + country. Verified against the live table; a name that stops matching
# is a MISS we report, never a near-miss we accept.
# Every pair below was read off the live table, and each was checked against a
# near-miss that must NOT be accepted:
#   EGCO   is "The Electricity Generating Public Company Limited", NOT "Electricity
#          Generating Authority of Thailand (EGAT)" — a different, state-owned entity.
#   BGRIM  is "BGrimm Power PCL", NOT "BGRIMM Technology Co., Ltd." (unrelated, China).
#   PGAS   is "PT Perusahaan Gas Negara Tbk", NOT "PT Perusahaan Listrik Negara
#          (Persero)" (PLN, the state electricity utility).
#   RATCH  is "Ratch Group PCL", NOT "RATCHTHANI LEASING PCL" or "NEXIF RATCH ENERGY".
#   YTLP   is "YTL Power International Berhad", NOT the parent "YTL Corp".
#   U96    is "SembCorp Industries" in Singapore, NOT "Sembcorp Salalah Power & Water
#          Company SAOG" in Oman — which is why the country is part of the key.
#
# GULF (Gulf Development) and POW (PetroVietnam Power) have NO row in the table at all,
# so they are deliberately absent here rather than pinned to a lookalike.
#
# Of the eight pinned, only Tenaga Nasional carries an actual score (Climate C, 2025).
# The other seven read "Did not disclose" or "See disclosing organisation" — those are
# disclosure states, not grades, and NON_SCORES keeps them out of the rater channel while
# still letting the UI say "did not disclose", which is itself a fact worth showing.
PINNED = {
    "U96":   ("SembCorp Industries", "Singapore"),
    "TNB":   ("Tenaga Nasional", "Malaysia"),
    "YTLP":  ("YTL Power International Berhad", "Malaysia"),
    "EGCO":  ("The Electricity Generating Public Company Limited", "Thailand"),
    "RATCH": ("Ratch Group PCL", "Thailand"),
    "BGRIM": ("BGrimm Power PCL", "Thailand"),
    "PGAS":  ("PT Perusahaan Gas Negara Tbk", "Indonesia"),
    "POWR":  ("CIKARANG LISTRINDO TBK PT", "Indonesia"),
}

# Non-score cells, normalised. These are disclosure states, not grades.
NON_SCORES = {
    "did not disclose": "did_not_disclose",
    "not scored": "not_scored",
    "see disclosing organisation": "see_parent",
    "": "absent",
}

_ICON = re.compile(r"/(?:Climate|Forests|Water)-([A-D])(-(?:minus|Minus))?-Icon", re.IGNORECASE)
_TITLE_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def parse_cell(cell: str) -> tuple[str | None, str | None]:
    """One table cell -> (letter grade, status). Exactly one of the two is set.

    A grade we cannot map is NOT silently downgraded to a status: it comes back as
    ("", "unrecognised") so the caller can report it instead of dropping it."""
    text = (cell or "").strip()
    if text.startswith("http"):
        match = _ICON.search(text)
        if not match:
            return "", "unrecognised"
        letter = match.group(1).upper() + ("-" if match.group(2) else "")
        if letter not in config.CDP_LETTER_TO_NUM:
            return "", "unrecognised"
        return letter, None
    status = NON_SCORES.get(text.lower())
    return (None, status) if status else ("", "unrecognised")


def _flourish_blob(html: str, name: str) -> dict:
    match = re.search(re.escape(name) + r"\s*=\s*", html)
    if not match:
        raise ValueError(f"{name} not found — CDP's embed changed shape")
    return json.JSONDecoder().raw_decode(html[match.end():])[0]


def _dataset_year(html: str, default: int) -> int:
    """The assessment year, taken from the visualisation's own title (e.g. "Public corp
    scores 2025 APPEALS"). Never assumed to be "now"."""
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    years = _TITLE_YEAR.findall(match.group(1)) if match else []
    return int(max(years)) if years else default


def parse_scores(html: str) -> dict:
    """The pinned companies' climate scores out of a fetched embed page."""
    data = _flourish_blob(html, "_Flourish_data")
    names = _flourish_blob(html, "_Flourish_data_column_names")
    columns = names["rows"]["columns"]
    if THEME_COLUMN not in columns:
        raise ValueError(f"no {THEME_COLUMN!r} column in {columns}")
    theme_at = columns.index(THEME_COLUMN)
    year = _dataset_year(html, config.CURRENT_YEAR)

    wanted = {(name, country): cid for cid, (name, country) in PINNED.items()}
    found: dict[str, dict] = {}
    for row in data.get("rows", []):
        cells = row.get("columns") or []
        if len(cells) <= theme_at:
            continue
        cid = wanted.get((cells[0].strip(), cells[1].strip()))
        if not cid:
            continue
        letter, status = parse_cell(cells[theme_at])
        found[cid] = {
            "cdp": letter or None, "status": status, "assessment_year": year,
            "table_name": cells[0].strip(), "country": cells[1].strip(),
            "source": SOURCE, "url": HUMAN_URL, "dataset_url": SCORES_URL,
        }
    return found


# --------------------------------------------------------------------------- #
# cache
# --------------------------------------------------------------------------- #
def cached_cdp() -> dict:
    """{"fetched_at":..., "companies": {cid: {...}}} from disk, or {} if none."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def scored_by_year() -> dict[str, dict[int, dict[str, str]]]:
    """{cid: {assessment_year: {"cdp": letter}}} for SCORED companies only.

    "Did not disclose" is deliberately absent: it must not become a rater value, and it
    must not be counted as a real rating towards the consensus/divergence floor."""
    out: dict[str, dict[int, dict[str, str]]] = {}
    for cid, info in (cached_cdp().get("companies") or {}).items():
        letter, year = info.get("cdp"), info.get("assessment_year")
        if letter and isinstance(year, int):
            out.setdefault(cid, {})[year] = {"cdp": letter}
    return out


def disclosure_status() -> dict[str, dict]:
    """{cid: info} for companies the table lists WITHOUT a score — the honest reason a
    CDP channel is empty, which the UI can show instead of a blank."""
    return {cid: info for cid, info in (cached_cdp().get("companies") or {}).items()
            if not info.get("cdp")}


# --------------------------------------------------------------------------- #
# ingest overlay
# --------------------------------------------------------------------------- #
def discrepancies() -> list[dict]:
    """Company-years where this table and a report-disclosed CDP score disagree.

    The report wins (it carries a verbatim quote and a citable PDF), but a silent pick
    would hide a real conflict, so every clash is returned for logging."""
    try:
        from backend.data.realratings import scored_by_year as disclosed_by_year
    except Exception:
        return []
    disclosed = disclosed_by_year()
    out = []
    for cid, years in scored_by_year().items():
        for year, entries in years.items():
            row = disclosed.get(cid, {}).get(year, {}).get("cdp")
            if row and row.get("value_raw") and row["value_raw"] != entries["cdp"]:
                out.append({"company_id": cid, "year": year, "table": entries["cdp"],
                            "report": row["value_raw"], "report_url": row.get("source_url"),
                            "resolved_to": row["value_raw"]})
    return out


def overlay(raters: list) -> list:
    """Overlay CDP table scores onto their own assessment year.

    Applied BEFORE the report-disclosed overlay, so a report-disclosed score for the same
    company-year wins by simply overwriting this one — that is the precedence, and
    `discrepancies()` reports any case where the two actually differ."""
    from backend.engine.rater_overlay import apply

    return apply(raters, scored_by_year())


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def fetch_html(url: str = SCORES_URL, attempts: int = 4) -> str:
    """Fetch the embed page, retrying truncated reads.

    The response is ~4MB of chunked transfer and the server intermittently cuts it short,
    raising http.client.IncompleteRead. A short read must NOT be treated as the dataset:
    parse_scores would find no pinned rows and the caller would silently keep a stale
    cache, which is how a whole roster can read "NOT FOUND" while the table is fine.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                html = response.read().decode("utf-8", "replace")
        except Exception as exc:                     # IncompleteRead, timeouts, resets
            last = exc
            time.sleep(2 * (attempt + 1))
            continue
        if len(html) < _MIN_HTML_BYTES:
            last = ValueError(f"short read: {len(html)} bytes < {_MIN_HTML_BYTES}")
            time.sleep(2 * (attempt + 1))
            continue
        return html
    raise RuntimeError(f"CDP fetch failed after {attempts} attempts: {last}")


def build_real_cdp() -> dict:
    """Fetch, parse, and cache. A failed or empty fetch keeps the existing cache."""
    try:
        html = fetch_html()
        found = parse_scores(html)
    except Exception as exc:
        print(f"CDP fetch/parse failed ({type(exc).__name__}: {exc}) — keeping existing cache.")
        return cached_cdp().get("companies") or {}
    if not found:
        print("CDP table matched none of the pinned names — keeping existing cache.")
        return cached_cdp().get("companies") or {}
    CACHE_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE, "url": HUMAN_URL, "dataset_url": SCORES_URL,
        "terms": "internal, non-commercial use only; commercial use or public "
                 "redistribution requires prior written consent from CDP",
        "companies": found,
    }, ensure_ascii=False, indent=2), "utf-8")
    return found


def summary() -> str:
    cache = cached_cdp()
    companies = cache.get("companies") or {}
    lines = [f"  fetched_at {cache.get('fetched_at')}  <- {cache.get('url')}"]
    for cid, (name, _country) in PINNED.items():
        info = companies.get(cid)
        if not info:
            lines.append(f"  {cid:4} {name[:38]:38} NOT FOUND in the table")
        elif info.get("cdp"):
            lines.append(f"  {cid:4} {name[:38]:38} {info['cdp']:3} ({info['assessment_year']})")
        else:
            lines.append(f"  {cid:4} {name[:38]:38} -   {info.get('status')} (not a score)")
    for clash in discrepancies():
        lines.append(f"  ! {clash['company_id']} {clash['year']}: table={clash['table']} "
                     f"report={clash['report']} -> using the report-disclosed value")
    return "\n".join(lines)


def main() -> None:
    if "--show" not in sys.argv[1:]:
        found = build_real_cdp()
        print(f"CDP climate scores cached for {len(found)} companies -> {CACHE_FILE}")
    print(summary())
    print("\nRebuild the dashboard JSON:  python -m backend.engine.pipeline --offline")


if __name__ == "__main__":
    main()
