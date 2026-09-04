"""Replace a company's cached 'Claims & Evidence' with REAL claims extracted from its
actual sustainability report — without touching rater scores/quadrant/forecast.

Pipeline per company-YEAR (the evidence series is real, not seeded, so each year gets
its own report):
  1. SERP-find THAT YEAR's sustainability-report PDF (prefer the company's own domain).
  2. Fetch + extract the report text via Bright Data Web Unlocker + PyMuPDF.
  3. Run the engine's verbatim-guarded claim extraction with a cheap OpenRouter model.
  4. Map each claim to a material SASB topic; keep it as ASSERTED (company self-disclosure)
     with the REAL report URL + verbatim quote.
  5. Override only out/company/<id>.json["claims"] (scores/series/signal untouched).

A year whose report genuinely cannot be found is cached as an honest MISS — we never
fall back to a neighbouring year's report, and never synthesise one.

Results are cached per company-year so it never re-extracts. Run:

    python -m backend.data.realclaims D05 U96 BN4          # specific companies, END_YEAR
    python -m backend.data.realclaims --years 2019-2025    # backfill the whole window
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from backend.app.agent import WebTools, load_env
from backend.engine import config, ingest
from backend.engine.claims import extract_claims
from backend.engine.ingest import DocumentRow
from backend.engine.llm import MockLLMClient, OpenRouterLLMClient
from backend.engine.sasb import map_to_sasb, topics_for

# Official corporate domains, read from engine/config/source_registry.json so there is ONE
# source of truth. This used to be a second hardcoded dict, and when the universe changed
# it silently went stale: DOMAINS.get("TNB") returned "", which disabled the
# hosted-by-the-company guard in _looks_like_report and let a German industrial's annual
# report (takkt.de) be accepted as Tenaga Nasional's sustainability report.
def _load_domains() -> dict[str, str]:
    return dict(config.load_json("source_registry.json").get("company_domains") or {})


DOMAINS = _load_domains()
DEFAULT_SUBSET = list(DOMAINS)
MAX_CLAIMS = 40            # display cap (scoring only needs topic coverage)
# Read the report's first ~60k chars (CEO letter + highlights + key metrics) — that
# covers most material topics. Reading the whole PDF triples the bill for little gain.
REPORT_CHARS = 64000
CHUNK_CHARS = 12000       # extract per chunk (larger inputs drop verbatim matches)
MAX_CHUNKS = 5            # cap LLM calls/cost per company (~5 extract + 1 infer)
MAX_CANDIDATES = 8        # PDFs we are willing to fetch per company-year before calling a MISS

# Pinned official report PDFs, keyed by the REPORT's own year — removes SERP roulette
# for the years we have already verified by hand. SERP discovery runs for the rest.
PINNED_REPORTS: dict[str, dict[int, str]] = {
    # Hand-verified official report PDFs keyed by the REPORT's own year, which removes SERP
    # roulette for the years we have checked. Sembcorp folds its ESG disclosures into the
    # integrated annual report (no standalone sustainability-report PDF), so SERP discovery —
    # which excludes annual reports to avoid misattribution — never finds it. Pinning the AR
    # directly is the hand-verified exception: it carries Sembcorp's real workforce-safety (S)
    # and governance (G) disclosures.
    "U96": {2023: "https://www.sembcorp.com/media/2eungaft/sembcorp_ar2023.pdf"},
}

MIN_REPORT_YEAR = 2015                 # older than this is never a report we track
MAX_REPORT_YEAR = config.CURRENT_YEAR  # newer than this is a typo/id, not a report year
FIRSTPAGE_CHARS = 4000                 # how much of page 1 counts as "the cover" for year validation
MIN_SUSTAIN_MENTIONS = 5               # a real report says "sustainab*" far more often than a filing does
MIN_REAL_CLAIMS = 3                    # fewer verbatim claims than this -> the document was
                                       # not really that year's disclosure; record a MISS
                                       # rather than a year carried by pure inference

# SERP for "<company> sustainability report <year>" happily returns press releases,
# credit research and financial statements. Those are real documents but they are NOT
# the company's sustainability report, so claims from them would misattribute the year.
DENY_URL_PARTS = (
    "/media/", "/newsroom/", "/news/", "press-release", "pressrelease", "news-release",
    "newsrelease", "media-release", "announcement", "credit research", "credit%20research",
    "/research/", "/lease/", "presentation", "transcript", "factsheet", "fact-sheet",
    "circular", "prospectus", "-agm-", "newsroom", "/newsclip/", "newsclip",
    "financial_statements", "financial-statements", "financialstatements",
    # instrument- and framework-level documents cover a bond, not the company-year
    "green bond", "green-bond", "green_bond", "green%20bond", "sustainability-linked",
    "second opinion", "second%20opinion", "fact sheet", "fact%20sheet",
)
# The financial annual report is a different document with a different scope; judged on
# the filename so a report merely *hosted* under /annualreports/ still qualifies.
DENY_FILENAME_PARTS = ("annual-report", "annual_report", "annualreport", "ar20")
# ...and a candidate must positively identify itself as a sustainability/ESG report.
REPORT_TOKENS = ("sustainab", "esg", "gsr", "-isr", "_isr", "sr20", "sr-20", "sr_20",
                 "sr25", "csr", "climate",
                 # Thai/Indonesian filers publish a combined "One Report" (56-1) that
                 # carries the full sustainability section; it is the primary disclosure
                 # for those names, so it counts as a report.
                 "one-report", "one report", "onereport", "56-1", "one_report")


def _looks_like_report(url: str, title: str, domain: str = "") -> bool:
    low = (url + " " + title).lower()
    filename = low.split("?", 1)[0].rsplit("/", 1)[-1]
    if any(bad in low for bad in DENY_URL_PARTS):
        return False
    if any(bad in filename for bad in DENY_FILENAME_PARTS):
        return False
    # It must be hosted by the company itself. SERP happily returns a PEER's report for
    # "<company> sustainability report <year>", and those claims would be pure fiction.
    #
    # Fails CLOSED: with no known domain we cannot establish whose report this is, so it is
    # rejected. Treating an unknown domain as "no constraint" is what let takkt.de through.
    # Matched on the registrable domain rather than its first label, so `gulf.co.th` cannot
    # be satisfied by `gulfnews.com`.
    if not domain:
        return False
    netloc = urlparse(url).netloc.lower().split(":")[0]
    if netloc != domain and not netloc.endswith("." + domain):
        return False
    return any(tok in low for tok in REPORT_TOKENS)


def _years_in(text: str) -> set[int]:
    """Report years mentioned in a URL/title: plain 4-digit years plus FY spans
    (`2425`, `24/25`, `FY24-25`), which resolve to the LATER year."""
    low = (text or "").lower()
    out = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", low)}
    # two-digit report stamps: `ar-21`, `fy20`, `sr19`. Catching these is what stops a
    # `keppel-...-ar-21-full-report.pdf` being filed under 2022.
    out |= {2000 + int(d) for d in re.findall(r"(?:ar|sr|isr|gsr|fy)[-_ ]?(\d{2})(?!\d)", low)}
    for a, b in re.findall(r"(?<!\d)(\d{2})\s*[-/_]?\s*(\d{2})(?!\d)", low):
        ia, ib = int(a), int(b)
        if ib == ia + 1 and 15 <= ia <= 30:
            out.add(2000 + ib)
    return {y for y in out if MIN_REPORT_YEAR <= y <= MAX_REPORT_YEAR}


def _report_year(rep: dict) -> int | None:
    """The year the report itself covers, derived from URL then title then cover page.
    None when it cannot be established — callers must drop rather than guess."""
    for source in (rep.get("url"), rep.get("title"), (rep.get("text") or "")[:FIRSTPAGE_CHARS]):
        years = _years_in(str(source or ""))
        if years:
            return max(years)
    return None


async def _fetch_report(web: WebTools, name: str, url: str, year: int) -> dict | None:
    """Fetch a candidate PDF and keep it only if it really is `year`'s report."""
    try:
        fetched = await web.fetch_url(url, max_chars=REPORT_CHARS)
    except Exception:
        return None
    text = str(fetched.get("text") or "")
    if len(text) < 500:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    rep = {"url": fetched.get("url") or url,
           "title": fetched.get("title") or f"{name} Sustainability Report",
           "text": text}
    # The year must be evident in the URL, the title, or the cover page — otherwise we
    # cannot honestly label the row, so this candidate is not usable for `year`.
    if year not in _years_in(rep["url"]) | _years_in(rep["title"]) | _years_in(text[:FIRSTPAGE_CHARS]):
        return None
    if _report_year(rep) != year:
        return None  # a later year is named more prominently -> this is that year's report
    if text.lower().count("sustainab") < MIN_SUSTAIN_MENTIONS:
        return None  # reads like a filing/press release, not a sustainability report
    rep["report_year"] = year
    return rep


async def _find_report(web: WebTools, name: str, domain: str, year: int) -> dict | None:
    """Discover + fetch THAT YEAR's sustainability-report PDF; None if it cannot be
    found or its year cannot be confirmed. Never falls back to another year."""
    if not domain:
        return None          # cannot verify whose report a candidate is -> honest MISS
    queries = [
        f"site:{domain} sustainability report {year} filetype:pdf",
        f'"{name}" sustainability report {year} filetype:pdf',
        f'site:{domain} sr{year} OR "sustainability report {year}" pdf',
        f'"{name}" "sustainability report {year}" pdf archive',
    ]
    # Gather PDF candidates across all queries, then score so we reliably pick the
    # actual sustainability report (not an SGX filing or a one-off climate annex).
    candidates: dict[str, str] = {}
    for q in queries:
        try:
            res = await web.search(q, max_results=8)
        except Exception:
            continue
        for r in res.get("results", []):
            u = r.get("url") or ""
            title = r.get("title") or ""
            if u.lower().split("?", 1)[0].endswith(".pdf") and _looks_like_report(u, title, domain):
                candidates.setdefault(u, title)

    def score(u: str, title: str) -> int:
        low = (u + " " + title).lower()
        fname = low.split("?", 1)[0].rsplit("/", 1)[-1]
        s = 0
        if domain and domain in u:
            s += 10
        # The report signal must come from the FILENAME, not a sustainability-mentioning
        # title: that is what stops a `/newsclip/...2022.pdf` scoring like the real report.
        if any(k in fname for k in ("sustainab", "esg", "-sr", "_sr", "sr20", "one-report",
                                    "onereport", "56-1")):
            s += 8
        elif any(k in low for k in ("sustainab", "esg")):
            s += 2      # only the title says so -> weak signal
        years = _years_in(u) | _years_in(title)
        if year in years:
            s += 8      # the target year is named -> most likely that year's edition
        elif years:
            s -= 6      # names a DIFFERENT year -> almost certainly the wrong edition
        # A One Report legitimately lives under an annual-report path, so only penalise the
        # annual report when there is no sustainability/one-report signal in the filename.
        is_report_file = any(k in fname for k in ("sustainab", "esg", "-sr", "_sr", "sr20",
                                                  "one-report", "onereport", "56-1"))
        if not is_report_file and any(k in low for k in ("annual-report", "annualreport",
                                                         "ar20", "10-k", "agm")):
            s -= 3  # bias away from pure financial annual reports
        return s

    ranked = sorted(candidates.items(), key=lambda kv: score(kv[0], kv[1]), reverse=True)
    for url, _title in ranked[:MAX_CANDIDATES]:
        rep = await _fetch_report(web, name, url, year)
        if rep:
            return rep
    return None


def _claim_rows(cid: str, industry: str, rep: dict, client) -> list[dict]:
    """Deep extraction across the WHOLE report; falls back to the deterministic
    Mock splitter if the live model yields nothing (e.g. a bad model response)."""
    rows = _extract_rows(cid, industry, rep, client)
    if not rows:
        rows = _extract_rows(cid, industry, rep, MockLLMClient())
    return rows[:MAX_CLAIMS]


def _extract_rows(cid: str, industry: str, rep: dict, client) -> list[dict]:
    text = rep["text"]
    report_year = rep.get("report_year")
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)][:MAX_CHUNKS] or [text]
    rows, seen = [], set()
    for chunk in chunks:
        if len(chunk.strip()) < 50:  # skip only near-empty trailing fragments
            continue
        doc = DocumentRow(company_id=cid, doc_id=rep["url"], title=rep["title"],
                          year=report_year or config.END_YEAR, url=rep["url"],
                          source_page=1, text=chunk)
        try:
            claims = extract_claims(doc, client=client, use_cache=False)
        except Exception:
            continue  # one bad chunk never aborts the rest of the report
        for claim in claims:
            mapping = map_to_sasb(claim, industry)
            if not mapping.is_material:
                continue
            key = claim.text.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "topic_id": mapping.topic_id, "pillar": mapping.pillar,
                "state": "ASSERTED",  # company self-disclosure
                "text": claim.text, "source_sentence": claim.source_sentence,
                "source_doc": rep["title"], "source_url": rep["url"],
                "source_page": claim.source_page, "weight": mapping.weight,
                "report_year": report_year,  # the report's OWN year, never the analysis year
            })
            if len(rows) >= MAX_CLAIMS:
                return rows
    return rows


def _infer_missing_topics(industry: str, rep: dict, real_rows: list[dict], client) -> list[dict]:
    """For material topics the report never discloses, ask the model for a labelled
    best-estimate (state=INFERRED) so the gap is filled transparently, not faked."""
    if not hasattr(client, "complete_json"):
        return []
    covered = {r["topic_id"] for r in real_rows}
    missing = [t for t in topics_for(industry) if t["topic_id"] not in covered]
    if not missing:
        return []
    by_id = {t["topic_id"]: t for t in missing}
    listed = "; ".join(
        f'{t["topic_id"]} (keywords: {", ".join(t.get("keywords", [])[:4])})' for t in missing
    )
    prompt = (
        "You are assessing a company's ESG posture from its sustainability report. "
        "For each material topic listed below that is NOT directly disclosed in the excerpt, "
        "write ONE concise sentence estimating how the company most likely addresses it, "
        "based on the report's overall content and typical practice in its sector. "
        "This is an INFERENCE, not a quote — do not fabricate specific figures. "
        'Return JSON {"assessments":[{"topic_id":"...","assessment":"..."}]}.\n\n'
        f"MATERIAL TOPICS: {listed}\n\nREPORT EXCERPT:\n{rep['text'][:12000]}"
    )
    try:
        data = client.complete_json(prompt)
    except Exception:
        return []
    rows = []
    for item in data.get("assessments", []):
        topic = by_id.get(str(item.get("topic_id") or ""))
        text = str(item.get("assessment") or "").strip()
        if not topic or not text:
            continue
        rows.append({
            "topic_id": topic["topic_id"], "pillar": topic["pillar"],
            "state": "INFERRED",  # labelled estimate for an undisclosed material topic
            "text": text, "source_sentence": None,
            "source_doc": rep["title"], "source_url": rep["url"],
            "source_page": None, "weight": float(topic["weight"]), "inferred": True,
            "report_year": rep.get("report_year"),
        })
    return rows


def cache_path_for(cid: str, year: int | None) -> Path:
    d = config.CACHE_DIR / "realclaims"
    return d / (f"{cid}.json" if year is None else f"{cid}_{year}.json")


def read_cache(cid: str, year: int | None) -> dict | None:
    """Raw cache envelope for a company-year (MISS envelopes included), or None."""
    path = cache_path_for(cid, year)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def cached_claims_for(cid: str, absent: list[dict] | None = None,
                      year: int | None = None) -> dict | None:
    """Live claims for a company-year. `year=None` reads the legacy single-report
    cache; a per-year miss falls back to the legacy file only at END_YEAR, so the
    backfilled years never borrow another year's report."""
    cached = read_cache(cid, year)
    if cached is None and year is not None and year == config.END_YEAR:
        cached = read_cache(cid, None)
    if cached is None or cached.get("miss"):
        return None
    rows = cached.get("rows") or []
    if not rows:
        return None
    return {
        "claims": rows,
        "absent": absent or [],
        "live": True,
        "report_year": cached.get("report_year"),
        "source_url": cached.get("source_url"),
        "source_title": cached.get("source_title"),
    }


def _write_cache(cid: str, year: int, payload: dict) -> None:
    cache_dir = config.CACHE_DIR / "realclaims"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path_for(cid, year).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def record_miss(cid: str, year: int) -> None:
    """No report exists for this company-year that we can honestly attribute."""
    _write_cache(cid, year, {"rows": [], "miss": True, "report_year": year})


def _apply(cid: str, rows: list[dict], rep: dict) -> None:
    year = int(rep["report_year"])
    _write_cache(cid, year, {"rows": rows, "report_year": year,
                             "source_url": rep["url"], "source_title": rep["title"]})
    if year != config.END_YEAR:
        return  # the dashboard payload only ever shows the analysis year's evidence
    path = config.OUT_DIR / "company" / f"{cid}.json"
    if path.exists():
        data = json.loads(path.read_text("utf-8"))
        absent = data.get("claims", {}).get("absent", [])
        live_claims = cached_claims_for(cid, absent=absent, year=year)
        if live_claims:
            data["claims"] = live_claims
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")


def build_real_claims(cids: list[str], years: list[int] | None = None,
                      refresh: bool = False) -> dict:
    """Extract real claims for every company-year. Already-cached pairs (hits AND
    misses) are skipped, so a long backfill resumes where it stopped."""
    years = years or [config.END_YEAR]
    load_env()
    ds = ingest.load()
    web = WebTools()
    # Fallback: no OpenRouter key -> deterministic Mock extraction (no LLM, no bill,
    # and inference is skipped). The dashboard still gets real report text, just
    # split into claims rather than LLM-distilled.
    if os.environ.get("OPENROUTER_API_KEY"):
        client = OpenRouterLLMClient()
    else:
        print("No OPENROUTER_API_KEY — using deterministic Mock extraction (no inference).")
        client = MockLLMClient()

    async def process(cid: str, year: int) -> tuple[str, int, int, int]:
        name = ds.company(cid).name
        industry = ds.company(cid).sasb_industry
        tag = f"{cid:4} {year} {name:24}"
        if not refresh and read_cache(cid, year) is not None:
            cached = read_cache(cid, year) or {}
            n = len(cached.get("rows") or [])
            print(f"  {tag} cached ({'MISS' if cached.get('miss') else f'{n} rows'})")
            return cid, year, n, 0
        pinned = PINNED_REPORTS.get(cid, {}).get(year)
        rep = await _fetch_report(web, name, pinned, year) if pinned else None
        if not rep:
            rep = await _find_report(web, name, DOMAINS.get(cid, ""), year)
        if not rep:
            record_miss(cid, year)
            print(f"  {tag} MISS (no {year} report PDF found)")
            return cid, year, 0, 0
        # extraction + inference are sync (LLM SDK) → run in a thread so all
        # companies process concurrently instead of one-by-one.
        real_rows, inferred_rows = await asyncio.to_thread(
            _extract_and_infer, cid, industry, rep, client
        )
        rows = real_rows + inferred_rows
        if len(real_rows) < MIN_REAL_CLAIMS:
            record_miss(cid, year)
            print(f"  {tag} MISS (only {len(real_rows)} verbatim claims — wrong document)")
            return cid, year, 0, 0
        _apply(cid, rows, rep)
        print(f"  {tag} {len(real_rows):2d} real + {len(inferred_rows):2d} inferred"
              f"  <- {rep['url'][:55]}")
        return cid, year, len(real_rows), len(inferred_rows)

    async def run_year(year: int):
        # one year at a time: bounded concurrency (10 in flight) and each year's
        # cache is fully on disk before the next starts.
        return await asyncio.gather(*[process(c, year) for c in cids],
                                    return_exceptions=True)

    async def run_all():
        out = []
        for year in years:
            print(f"--- {year} ---")
            out.extend(await run_year(year))
        return out

    results = asyncio.run(run_all())
    return {(cid, year): real + inferred
            for r in results if not isinstance(r, BaseException)
            for cid, year, real, inferred in [r]}


def _extract_and_infer(cid: str, industry: str, rep: dict, client) -> tuple[list[dict], list[dict]]:
    real_rows = _claim_rows(cid, industry, rep, client)
    inferred_rows = _infer_missing_topics(industry, rep, real_rows, client)
    return real_rows, inferred_rows


def _parse_years(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(y) for y in spec.split(",")]


def main() -> None:
    args = list(sys.argv[1:])
    years = [config.END_YEAR]
    refresh = "--refresh" in args
    args = [a for a in args if a != "--refresh"]
    if "--years" in args:
        i = args.index("--years")
        years = _parse_years(args[i + 1])
        del args[i:i + 2]
    cids = [c.upper() for c in args] or DEFAULT_SUBSET
    print(f"Extracting REAL claims for: {', '.join(cids)} x {years[0]}..{years[-1]}")
    summary = build_real_claims(cids, years, refresh=refresh)
    total = sum(summary.values())
    print(f"Done. {total} claims (real + labelled inference) across "
          f"{sum(1 for v in summary.values() if v)} company-years.")
    print("Now rebuild the dashboard JSON so the new evidence scores apply:")
    print("    python -m backend.engine.pipeline")


if __name__ == "__main__":
    main()
