"""REAL rater ratings extracted from the companies' OWN sustainability reports.

The rating agencies' own pages are no longer usable: KnowESG dropped its numeric scores,
Sustainalytics retired its free lookup, and S&P Global sits behind a bot wall we will not
try to defeat. But companies disclose their ratings themselves, in the reports this
project already fetches and already trusts as a source — e.g. Sembcorp's SR2024:

    "Received a rating of AA in the MSCI ESG Ratings assessment in 2024"

so the rating comes with a verbatim sentence, a citable URL, and a stated assessment year.

INVARIANTS (same as claim extraction, guardrail T7):
  * The sentence must be an exact substring of the fetched report text.
  * The sentence must name BOTH the rater and the value. "MSCI ESG Leaders constituent"
    is an index membership, not a rating — recorded as such, never scored.
  * The year attributed is the ASSESSMENT year the sentence states, not the report's
    publication year. Sembcorp's SR2024 carries a 2024 MSCI rating AND a 2023 CDP score.
  * A company that does not disclose gets nothing. Never inferred, never carried forward
    from another year or another company.

Because each year's report states that year's ratings, running this over several report
years yields a REAL rating time series — so percentiles/consensus/divergence can be
computed per year from real data instead of one undated value.

    python -m backend.data.realratings                    # all companies, END_YEAR report
    python -m backend.data.realratings --years 2022-2025  # build the time series
    python -m backend.data.realratings --matrix           # print coverage, fetch nothing
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from backend.app.agent import WebTools, load_env
from backend.data import realclaims
from backend.data.realclaims import DOMAINS, PINNED_REPORTS, _find_report
from backend.engine import config, ingest
from backend.engine.llm import OpenRouterLLMClient

DEFAULT_SUBSET = list(DOMAINS)
CACHE_SUBDIR = "realratings"

# Channels that carry a comparable numeric scale and therefore feed the rater percentiles.
SCORED_RATERS = ("msci", "sustainalytics", "sp", "cdp")
# Grade letters are UPPERCASE and stand alone. Without the boundary guards the CDP
# alternation happily matched the trailing "d" of "received" — the rater name and the
# keyword are case-insensitive (scoped (?i:)), the grade itself is not.
# The lookbehind also bars a preceding hyphen, or "the highest triple-A rating" reads as
# a rating of "A" — the opposite of what the sentence says.
_MSCI_LETTER = r"(?<![A-Za-z-])(AAA|AA|A|BBB|BB|B|CCC)(?![A-Za-z])"
_CDP_LETTER = r"(?<![A-Za-z-])(A-|A|B-|B|C-|C|D-|D)(?![A-Za-z-])"
_SCORE_WORD = r"(?i:\b(?:score|rating|rated|ranking|grade|band))"

# Regex first: cheap, deterministic, and it never invents a sentence. Each pattern must
# capture the VALUE and must sit in the same sentence as the rater's name.
PATTERNS: dict[str, tuple[str, ...]] = {
    "msci": (
        rf"(?i:MSCI)[^.]{{0,90}}?{_SCORE_WORD}\s*(?i:of|:)?\s*['\"‘“]?{_MSCI_LETTER}",
        rf"{_SCORE_WORD}\s*(?i:of|:)?\s*['\"‘“]?{_MSCI_LETTER}[^.]{{0,90}}?(?i:MSCI)",
        rf"(?i:MSCI\s+ESG\s+Ratings?)[^.]{{0,40}}?{_MSCI_LETTER}",
        rf"{_MSCI_LETTER}\s+(?i:rating)[^.]{{0,90}}?(?i:MSCI)",
        # "retain the 'AAA' leader rating by MSCI" / "Maintained 'AAA' ranking in MSCI
        # ESG Ratings" — quoted value, then the score word, then the rater.
        rf"['\"‘“]{_MSCI_LETTER}['\"’”][^.]{{0,40}}?{_SCORE_WORD}[^.]{{0,60}}?(?i:MSCI)",
    ),
    "cdp": (
        rf"(?i:CDP)[^.]{{0,140}}?{_SCORE_WORD}[^.]{{0,40}}?['\"‘“]?{_CDP_LETTER}",
        rf"{_SCORE_WORD}\s*(?i:of|:)?\s*['\"‘“]?{_CDP_LETTER}[^.]{{0,140}}?(?i:CDP)",
        # "...CDP Climate Change disclosure 'A' score" — value before the score word. The
        # quotes are required here; without them the window is too loose to trust.
        rf"(?i:CDP)[^.]{{0,140}}?['\"‘“]{_CDP_LETTER}['\"’”]\s*{_SCORE_WORD}",
    ),
    "sustainalytics": (
        r"(?i:Sustainalytics)[^.]{0,140}?(?i:\b(?:risk\s+rating|rating|rated|score))[^.]{0,30}?(?<!\d)(\d{1,2}(?:\.\d{1,2})?)\b",
        r"(?i:\bESG\s+Risk\s+Rating)\s*(?i:of|:)?\s*(?<!\d)(\d{1,2}(?:\.\d{1,2})?)\b[^.]{0,140}?(?i:Sustainalytics)",
    ),
    "sp": (
        r"(?i:S&P\s+Global)[^.]{0,140}?(?i:\b(?:ESG\s+)?(?:score|rating))[^.]{0,30}?(?<!\d)(\d{1,3}(?:\.\d)?)\b",
        # CSA needs a hard word boundary: without it "CSAT score of 72.0" — an airline's
        # CUSTOMER-satisfaction score — was filed as an S&P Global CSA result.
        r"(?i:\b(?:CSA(?!\w)|Corporate\s+Sustainability\s+Assessment))[^.]{0,80}?(?i:\bscore)\s*(?i:of|:)?\s*(?<!\d)(\d{1,3}(?:\.\d)?)\b",
    ),
}

# Index memberships. Real and worth recording, but a constituent list is not a rating and
# has no scale, so these never enter consensus/divergence.
MEMBERSHIP_PATTERNS: dict[str, str] = {
    "djsi": r"(Dow\s+Jones\s+(?:Best[- ]In[- ]Class|Sustainability)[^.]{0,60}|DJSI[^.]{0,60})",
    "ftse4good": r"(FTSE4Good[^.]{0,60})",
}

MAX_SENTENCE_CHARS = 400        # beyond this a "sentence" is a run-on page of PDF layout
WINDOW_STRIDE = 250             # overlap step when a run-on has to be windowed
# PDF text extraction rarely gives clean sentences: award and highlight pages are bullet
# runs with no full stops at all, which is exactly where ratings are disclosed. So split
# on bullet glyphs and pipes as well as terminators, and window whatever is still too
# long rather than dropping it — every window is still a verbatim substring.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\s*[•●▪◆■|]\s*|\s{3,}")


# --------------------------------------------------------------------------- #
# extraction
# --------------------------------------------------------------------------- #
def _sentences(text: str) -> list[str]:
    out = []
    for raw in _SENTENCE_SPLIT.split(text or ""):
        seg = (raw or "").strip()
        if len(seg) < 20:
            continue
        if len(seg) <= MAX_SENTENCE_CHARS:
            out.append(seg)
            continue
        for i in range(0, len(seg), WINDOW_STRIDE):     # overlapping verbatim windows
            window = seg[i:i + MAX_SENTENCE_CHARS].strip()
            if len(window) >= 20:
                out.append(window)
    return out


_STREAK_YEAR = re.compile(r"(?i:since|from|for\s+the\s+past)\s+(?:\w+\s+){0,2}?(20\d{2})")


def _assessment_year(sentence: str, report_year: int) -> int:
    """The year the sentence itself states, else the report's own year. Sembcorp's CDP
    score is "received in 2023" inside the 2024 report — that rating belongs to 2023.

    A year introduced by "since"/"from" is the START of a streak, not the assessment:
    "retained AAA since 2020" in the 2024 report is a 2024 rating, so those are ignored.
    """
    spans = {m.group(1) for m in _STREAK_YEAR.finditer(sentence)}
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", sentence) if y not in spans]
    years = [y for y in years if 2010 <= y <= config.CURRENT_YEAR]
    return max(years) if years else report_year


def _valid_value(rater: str, raw: str) -> str | None:
    """Check the captured value against that rater's own scale; None if it is off-scale
    (a false positive from a stray letter or a page number)."""
    raw = raw.strip().upper()
    if rater == "msci":
        return raw if raw in config.MSCI_LETTER_TO_NUM else None
    if rater == "cdp":
        return raw if raw in config.CDP_LETTER_TO_NUM else None
    try:
        number = float(raw)
    except ValueError:
        return None
    top = config.SUSTAINALYTICS_MAX if rater == "sustainalytics" else config.SP_GLOBAL_MAX
    if not 0.0 < number <= top:
        return None
    return f"{round(number, 2):g}"


def _span(segment: str, match: re.Match, end: int | None = None) -> str:
    """The matched text, snapped outward to word boundaries so it reads cleanly. Still an
    exact substring of the report, so the verbatim invariant holds."""
    start, end = match.start(), match.end() if end is None else end
    while start > 0 and segment[start - 1].isalnum():
        start -= 1
    while end < len(segment) and segment[end].isalnum():
        end += 1
    return segment[start:end].strip()


# "MSCI ESG Ratings assessment (on a scale of AAA to CCC)" describes the SCALE, not the
# company's place on it — the endpoints of a stated range are never a rating.
_SCALE_LEAD = re.compile(r"(?i)(?:scale|range|band)\s+(?:of|from)\s*['\"‘“]?$")
_SCALE_TAIL = re.compile(r"(?i)^\s*(?:to|-|–)\s*(?:CCC|D-|D|0)")
_THRESHOLD_TAIL = re.compile(r"(?i)^\s*(?:and|or)\s+(?:above|higher|better|more)|^\s*\+")
_FROM_VALUE = re.compile(r"(?i)\bfrom\s+['\"‘“]?[A-Za-z0-9.\-]{1,6}$")
# A capitalised name in the subject slot of "<X> achieved/received/maintains ..." means the
# report is describing SOMEBODY ELSE's rating. Singtel's SR2025 profiles its Thai associate
# AIS ("AIS maintains 'AA' ESG ratings from SET and MSCI"); that is AIS's rating, and
# filing it under Singtel would invent an upgrade.
_SUBJECT = re.compile(r"\b([A-Z][A-Za-z&.\-']{1,24})\s+(?:maintains?|maintained|achiev\w+|"
                      r"receiv\w+|holds?|has|have|had|is|was|were|reported|scored|earned|"
                      r"retained|secured|obtained)\s")
_SELF_SUBJECTS = {"we", "our", "us", "the", "this", "it", "its", "they", "group", "company",
                  "in", "and", "a", "an", "there", "both", "all", "who", "which", "that",
                  "esg", "msci", "cdp", "sustainalytics", "sp", "rating", "ratings", "score"}


def _is_threshold(sentence: str, match: re.Match) -> bool:
    """"MSCI ESG ratings of BBB and above" is an eligibility CRITERION for the bank's
    sustainable-investment products, not a rating the bank received."""
    tail = sentence[match.end():match.end() + 20]
    return bool(_THRESHOLD_TAIL.match(tail) or _SCALE_TAIL.match(tail)
                or _SCALE_LEAD.search(sentence[:match.start()][-24:]))


def _retarget_upgrade(rater: str, sentence: str, match: re.Match,
                      value: str) -> tuple[str | None, int]:
    """"improved our CDP Climate Change score from C to B- in 2019" discloses B-. The value
    after "from" is the score being left behind — record the new one, or nothing."""
    if not _FROM_VALUE.search(match.group(0)):
        return value, match.end()
    tail = re.match(r"\s*to\s+['\"‘“]?([A-Za-z0-9.\-]{1,6})", sentence[match.end():])
    if not tail:
        return None, match.end()
    # widen the recorded span to the NEW value, or the verbatim sentence would name a
    # score the row does not claim
    return _valid_value(rater, tail.group(1)), match.end() + tail.end()


def _third_party(sentence: str, company: str) -> bool:
    """True when the sentence attributes the rating to a named party that is not this
    company (a subsidiary profile, an associate, a peer)."""
    if not company:
        return False
    own = {w.lower() for w in re.findall(r"[A-Za-z&]+", company)}
    for m in _SUBJECT.finditer(sentence):
        word = m.group(1).lower()
        if word not in own and word not in _SELF_SUBJECTS:
            return True
    return False


def _wrong_theme(rater: str, sentence: str) -> bool:
    """CDP scores several themes separately — Climate Change, Water Security, Forests.
    Only the climate score belongs in this channel; a Water Security 'B' filed as a CDP
    rating would be a different measurement wearing the same label."""
    if rater != "cdp":
        return False
    low = sentence.lower()
    if any(theme in low for theme in ("water", "forest", "supplier engagement")):
        return "climate" not in low
    return "climate" not in low


def _row(rater: str, value: str, sentence: str, report_year: int, url: str, title: str,
         extractor: str, seen: set, company: str = "") -> dict | None:
    """Build one rating row, applying the theme guard, the year rule and the dedupe that
    BOTH extractors must obey. Returns None when the candidate must be dropped."""
    if _wrong_theme(rater, sentence) or _third_party(sentence, company):
        return None
    year = _assessment_year(sentence, report_year)
    if (rater, year) in seen:
        return None
    seen.add((rater, year))
    return {"rater": rater, "kind": "rating", "value_raw": value,
            "assessment_year": year, "report_year": report_year,
            "source_url": url, "source_title": title,
            "source_sentence": sentence, "extractor": extractor}


def extract_ratings(text: str, report_year: int, url: str, title: str,
                    seen: set | None = None, company: str = "") -> list[dict]:
    """Every disclosed rating + index membership in a report's text, regex-first.

    Only sentences drawn from `text` are ever returned, so the verbatim invariant holds
    by construction; the LLM fallback re-checks it explicitly.
    """
    rows: list[dict] = []
    seen = seen if seen is not None else set()
    for sentence in _sentences(text):
        # Checked on the WHOLE sentence, not the matched span: the span is snapped to the
        # rater + value and would drop the "AIS maintains ..." subject that gives the
        # rating away as somebody else's.
        if _third_party(sentence, company):
            continue
        for rater, patterns in PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, sentence)
                if not match:
                    continue
                value = _valid_value(rater, match.group(1))
                if value is None or _is_threshold(sentence, match):
                    continue
                value, end = _retarget_upgrade(rater, sentence, match, value)
                if value is None:
                    continue
                # Record the MATCHED SPAN, not the whole window. A window can hold two
                # disclosures — Sembcorp's page carries a 2023 CDP score and a 2024 MSCI
                # rating side by side — and taking the window's latest year would file
                # the CDP score under 2024. The span still names the rater and the value,
                # and is still a verbatim substring.
                row = _row(rater, value, _span(sentence, match, end), report_year, url, title,
                           "regex", seen, company)
                if row:
                    rows.append(row)
                break
        for rater, pattern in MEMBERSHIP_PATTERNS.items():
            match = re.search(pattern, sentence, re.IGNORECASE)
            if not match or (rater, report_year) in seen:
                continue
            seen.add((rater, report_year))
            rows.append({
                # no scale, so this is disclosure context for the UI — never a score.
                # The span, not the window: a bullet run can carry a CEO sign-off and a
                # stray date, and neither belongs in the membership's citation or year.
                "rater": rater, "kind": "membership", "value_raw": match.group(1).strip(),
                "assessment_year": min(_assessment_year(_span(sentence, match), report_year),
                                       report_year),
                "report_year": report_year, "source_url": url, "source_title": title,
                "source_sentence": _span(sentence, match), "extractor": "regex",
            })
    return rows


LLM_PROMPT = (
    "Below is text from a company's sustainability report. List ONLY the ESG rating "
    "scores the company states it RECEIVED, from these raters: MSCI (letter CCC..AAA), "
    "Sustainalytics (ESG Risk Rating number), S&P Global (score 0-100), CDP (letter D-..A). "
    "For each, quote the sentence EXACTLY as it appears — do not paraphrase, do not fix "
    "spacing. Skip index memberships and any rater mentioned without a value. If none "
    'are stated, return an empty list. JSON: {"ratings":[{"rater":"msci",'
    '"value":"AA","year":2024,"sentence":"..."}]}\n\nREPORT TEXT:\n'
)


_RATER_MENTION = re.compile(r"(?i:MSCI|CDP|Sustainalytics|S&P\s+Global|Corporate\s+Sustainability\s+Assessment)")
LLM_EXCERPT_CHARS = 12000      # what the fallback model is shown (cost cap)
LLM_WINDOW = 500               # context kept either side of a rater mention


def _rater_excerpt(text: str, limit: int = LLM_EXCERPT_CHARS) -> str:
    """The passages that actually mention a rater, not the report's first N chars. A full
    report is now read end-to-end, so the ratings page is rarely in the opening pages."""
    spans: list[tuple[int, int]] = []
    for m in _RATER_MENTION.finditer(text):
        lo, hi = max(0, m.start() - LLM_WINDOW), min(len(text), m.end() + LLM_WINDOW)
        if spans and lo <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], hi))
        else:
            spans.append((lo, hi))
    out = " ... ".join(text[lo:hi] for lo, hi in spans)
    return (out or text)[:limit]


def _llm_ratings(text: str, report_year: int, url: str, title: str, client,
                 seen: set | None = None, company: str = "") -> list[dict]:
    """Fallback for phrasings the regexes miss. Every row is re-validated against the
    source text — a quote the model altered is dropped, not repaired — and then goes
    through the same theme/year/dedupe rules as the regex path."""
    seen = seen if seen is not None else set()
    if not hasattr(client, "complete_json"):
        return []
    try:
        data = client.complete_json(LLM_PROMPT + _rater_excerpt(text))
    except Exception:
        return []
    rows = []
    for item in data.get("ratings", []) or []:
        rater = str(item.get("rater") or "").strip().lower()
        sentence = str(item.get("sentence") or "").strip()
        if rater not in SCORED_RATERS or not sentence:
            continue
        if sentence not in text:                      # verbatim invariant — no repair
            continue
        value = _valid_value(rater, str(item.get("value") or ""))
        if value is None:
            continue
        # A bare substring test is useless for one-letter grades: "C0. Introduction" in a
        # CDP questionnaire cover page happily "contains" a C. The value must appear as a
        # standalone grade, and the sentence must actually be about a score.
        letters = {"msci": _MSCI_LETTER, "cdp": _CDP_LETTER}.get(rater)
        if letters is not None:
            if value not in [m.group(1) for m in re.finditer(letters, sentence)]:
                continue
        elif value.upper() not in sentence.upper():
            continue
        if not re.search(_SCORE_WORD, sentence):
            continue
        if rater == "sp":
            names = ("S&P", "CSA", "Corporate Sustainability Assessment")
        else:
            names = {"msci": ("MSCI",), "cdp": ("CDP",),
                     "sustainalytics": ("Sustainalytics",)}[rater]
        if not any(n.lower() in sentence.lower() for n in names):
            continue                                   # ...and must name the rater
        row = _row(rater, value, sentence, report_year, url, title, "llm", seen, company)
        if row:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# cache
# --------------------------------------------------------------------------- #
def _known_report_urls(cid: str, report_year: int) -> list[str]:
    """Report URLs already verified for this company-year — the pinned PDF, then the one
    realclaims recorded when it extracted that year's claims. Companies reprint their
    ratings page every year, so those older reports carry the older ratings; re-using the
    URL avoids a second round of SERP roulette and inherits realclaims' year check."""
    urls: list[str] = []
    pinned = PINNED_REPORTS.get(cid, {}).get(report_year)
    if pinned:
        urls.append(pinned)
    cached = realclaims.read_cache(cid, report_year) or {}
    if not cached.get("miss"):
        for candidate in [cached.get("source_url")] + [r.get("source_url") for r in cached.get("rows") or []]:
            if candidate and candidate not in urls:
                urls.append(candidate)
    return urls


async def _deep_fetch(web, name: str, url: str, report_year: int) -> dict | None:
    """Read a KNOWN report end-to-end. realclaims stops at its 64k claim window, but the
    ratings/awards page usually sits deep in the PDF — that truncation, not silence, is
    why most company-years looked ratings-free. The year is not re-derived here: these
    URLs were already year-verified when they were recorded."""
    try:
        fetched = await web.fetch_url(url, max_chars=config.RATINGS_REPORT_CHARS)
    except Exception:
        return None
    text = re.sub(r"\s+", " ", str(fetched.get("text") or "")).strip()
    if len(text) < 500:
        return None
    return {"url": fetched.get("url") or url, "text": text,
            "title": fetched.get("title") or f"{name} Sustainability Report {report_year}"}


def cache_path_for(cid: str, report_year: int) -> Path:
    return config.CACHE_DIR / CACHE_SUBDIR / f"{cid}_{report_year}.json"


def read_cache(cid: str, report_year: int) -> dict | None:
    path = cache_path_for(cid, report_year)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def _write_cache(cid: str, report_year: int, payload: dict) -> None:
    path = cache_path_for(cid, report_year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def all_cached() -> dict[str, list[dict]]:
    """{cid: [row, ...]} across every cached report year (MISS envelopes excluded)."""
    out: dict[str, list[dict]] = {}
    directory = config.CACHE_DIR / CACHE_SUBDIR
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*_*.json")):
        try:
            payload = json.loads(path.read_text("utf-8"))
        except Exception:
            continue
        cid = payload.get("company_id") or path.stem.rsplit("_", 1)[0]
        out.setdefault(cid, []).extend(payload.get("rows") or [])
    return out


def scored_by_year() -> dict[str, dict[int, dict[str, dict]]]:
    """{cid: {assessment_year: {rater: row}}} for the SCORED channels only.

    When two reports state the same company-rater-year (the 2024 and 2025 reports both
    recalling a 2024 rating), the later report wins — it is the more recent restatement.
    """
    out: dict[str, dict[int, dict[str, dict]]] = {}
    for cid, rows in all_cached().items():
        for row in sorted(rows, key=lambda r: r.get("report_year") or 0):
            if row.get("kind") != "rating" or row.get("rater") not in SCORED_RATERS:
                continue
            year = row.get("assessment_year")
            if not isinstance(year, int):
                continue
            out.setdefault(cid, {}).setdefault(year, {})[row["rater"]] = row
    return out


def real_keys_by_company_year() -> dict[str, dict[int, list[str]]]:
    """{cid: {year: [rater, ...]}} — which channels a report vouches for, per year."""
    return {cid: {year: sorted(raters) for year, raters in years.items()}
            for cid, years in scored_by_year().items()}


# --------------------------------------------------------------------------- #
# ingest overlay
# --------------------------------------------------------------------------- #
def overlay(raters: list) -> list:
    """Overlay report-disclosed ratings onto the row for their OWN assessment year.

    Unlike the KnowESG cache this is not pinned to END_YEAR: each report states that
    year's ratings, so the overlay lands per year and builds a genuine series. Years the
    reports never mention keep whatever they had — nothing is carried forward.
    """
    from backend.engine.rater_overlay import apply

    return apply(raters, {cid: {year: {rater: row["value_raw"]
                                       for rater, row in entries.items()}
                                for year, entries in years.items()}
                          for cid, years in scored_by_year().items()})


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build_real_ratings(cids: list[str], years: list[int] | None = None,
                       refresh: bool = False, retry_miss: bool = False) -> dict[tuple[str, int], int]:
    """Fetch each company-year's report and extract the ratings it discloses. Cached
    company-years (hits AND misses) are skipped so a backfill resumes where it stopped."""
    years = years or [config.END_YEAR]
    load_env()
    ds = ingest.load()
    web = WebTools()
    client = OpenRouterLLMClient() if os.environ.get("OPENROUTER_API_KEY") else None
    if client is None:
        print("No OPENROUTER_API_KEY — regex extraction only (no LLM fallback).")

    async def process(cid: str, year: int) -> tuple[str, int, int]:
        name = ds.company(cid).name
        tag = f"{cid:4} {year} {name:26}"
        cached = read_cache(cid, year)
        stale_miss = retry_miss and (cached or {}).get("miss")
        if not refresh and not stale_miss and cached is not None:
            n = len(cached.get("rows") or [])
            print(f"  {tag} cached ({'MISS' if cached.get('miss') else f'{n} rows'})")
            return cid, year, n
        rep = None
        for url in _known_report_urls(cid, year):
            rep = await _deep_fetch(web, name, url, year)
            if rep:
                break
        if not rep and realclaims.read_cache(cid, year) is None:
            # realclaims already ran (and cached) the SERP hunt for every company-year in
            # the window; repeating it for one it recorded as a MISS just burns calls.
            rep = await _find_report(web, name, DOMAINS.get(cid, ""), year)
        if not rep:
            _write_cache(cid, year, {"company_id": cid, "report_year": year,
                                     "rows": [], "miss": True})
            print(f"  {tag} MISS (no {year} report PDF found)")
            return cid, year, 0
        text, url, title = rep["text"], rep["url"], rep["title"]
        seen: set = set()      # shared, so the LLM cannot re-file what the regex found
        rows = extract_ratings(text, year, url, title, seen, name)
        if client is not None and not any(r["kind"] == "rating" for r in rows):
            rows += await asyncio.to_thread(_llm_ratings, text, year, url, title, client, seen, name)
        _write_cache(cid, year, {"company_id": cid, "report_year": year, "rows": rows,
                                 "miss": not rows, "source_url": url, "source_title": title})
        scored = [r for r in rows if r["kind"] == "rating"]
        print(f"  {tag} {len(scored)} rating(s): "
              f"{', '.join(f'{r['rater']}={r['value_raw']}@{r['assessment_year']}' for r in scored) or '-'}")
        return cid, year, len(scored)

    async def run_all():
        out = []
        for year in years:
            print(f"--- report year {year} ---")
            out.extend(await asyncio.gather(*[process(c, year) for c in cids],
                                            return_exceptions=True))
        return out

    results = asyncio.run(run_all())
    return {(cid, year): n for r in results if not isinstance(r, BaseException)
            for cid, year, n in [r]}


def coverage_matrix(cids: list[str] | None = None) -> str:
    """company × rater × assessment-year -> value or MISS, straight from the cache."""
    cids = cids or DEFAULT_SUBSET
    by_year = scored_by_year()
    lines = []
    for cid in cids:
        years = by_year.get(cid, {})
        if not years:
            lines.append(f"  {cid:4} MISS (no disclosed ratings cached)")
            continue
        for year in sorted(years):
            cells = ", ".join(f"{rater}={row['value_raw']}"
                              for rater, row in sorted(years[year].items()))
            n_real = len(years[year])
            flag = "REAL DIVERGENCE" if n_real >= config.MIN_REAL_RATERS_FOR_DIVERGENCE else "1 rater only"
            lines.append(f"  {cid:4} {year}  {cells:52} [{n_real} real -> {flag}]")
    return "\n".join(lines)


def _parse_years(spec: str) -> list[int]:
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(y) for y in spec.split(",")]


def main() -> None:
    args = list(sys.argv[1:])
    refresh = "--refresh" in args
    retry_miss = "--retry-miss" in args
    matrix_only = "--matrix" in args
    args = [a for a in args if a not in ("--refresh", "--matrix", "--retry-miss")]
    years = [config.END_YEAR]
    if "--years" in args:
        i = args.index("--years")
        years = _parse_years(args[i + 1])
        del args[i:i + 2]
    cids = [c.upper() for c in args] or DEFAULT_SUBSET
    if not matrix_only:
        print(f"Extracting disclosed ratings for: {', '.join(cids)} x {years[0]}..{years[-1]}")
        build_real_ratings(cids, years, refresh=refresh, retry_miss=retry_miss)
    print("\nCoverage (company x assessment year):")
    print(coverage_matrix(cids))
    print("\nRebuild the dashboard JSON:  python -m backend.engine.pipeline --offline")


if __name__ == "__main__":
    main()
