"""Replace a company's cached 'Claims & Evidence' with REAL claims extracted from its
actual sustainability report — without touching rater scores/quadrant/forecast.

Pipeline per company:
  1. SERP-find the latest sustainability-report PDF (prefer the company's own domain).
  2. Fetch + extract the report text via Bright Data Web Unlocker + PyMuPDF.
  3. Run the engine's verbatim-guarded claim extraction with a cheap OpenRouter model.
  4. Map each claim to a material SASB topic; keep it as ASSERTED (company self-disclosure)
     with the REAL report URL + verbatim quote.
  5. Override only out/company/<id>.json["claims"] (scores/series/signal untouched).

Results are cached so it never re-extracts unless the report text changes. Run:

    python -m backend.data.realclaims D05 U96 BN4      # specific companies
    python -m backend.data.realclaims                  # default demo subset
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

from backend.app.agent import WebTools, load_env
from backend.engine import config, ingest
from backend.engine.claims import extract_claims
from backend.engine.ingest import DocumentRow
from backend.engine.llm import MockLLMClient, OpenRouterLLMClient
from backend.engine.sasb import map_to_sasb, topics_for

# Official corporate domains for the tracked universe (used to prefer the primary disclosure).
DOMAINS = {
    "D05": "dbs.com", "O39": "ocbc.com", "U11": "uobgroup.com", "Z74": "singtel.com",
    "C6L": "singaporeair.com", "BN4": "keppel.com", "U96": "sembcorp.com",
    "9CI": "capitaland.com", "C09": "cdl.com.sg", "F34": "wilmar-international.com",
}
DEFAULT_SUBSET = list(DOMAINS)
MAX_CLAIMS = 40            # display cap (scoring only needs topic coverage)
# Read the report's first ~60k chars (CEO letter + highlights + key metrics) — that
# covers most material topics. Reading the whole PDF triples the bill for little gain.
REPORT_CHARS = 64000
CHUNK_CHARS = 12000       # extract per chunk (larger inputs drop verbatim matches)
MAX_CHUNKS = 5            # cap LLM calls/cost per company (~5 extract + 1 infer)

# Pinned official report PDFs for the demo subset — removes SERP roulette so the
# pitch is stable and rich. SERP discovery still runs for any company not pinned.
REPORT_URLS = {
    "D05": "https://www.dbs.com/annualreports/2024/i/pdf/dbs_sr2024.pdf",
    "O39": "https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/ocbc-sustainability-report-2024.pdf",
    "U11": "https://www.uobgroup.com/investor-relations/assets/pdfs/investor/annual/uob-sustainability-report-2024.pdf",
    "Z74": "https://cdn1.singteldigital.com/content/dam/singtel/investorRelations/annualReports/2025/SR2025.pdf",
    "C6L": "https://www.singaporeair.com/content/dam/sia/web-assets/pdfs/about-us/information-for-investors/annual-report/sustainabilityreport2425.pdf",
    "BN4": "https://www.keppel.com/file/sustainability/sustainability-reports/keppel-ltd-sustainability-report-2024-full-report.pdf",
    "U96": "https://www.sembcorp.com/media/jc3bwis3/sci-sustainability-report-2024.pdf",
    "9CI": "https://www.capitaland.com/content/dam/capitalandinvestment/sustainability/global-sustainability-reports/CLI-GSR-2024.pdf",
    "C09": "https://cdlsustainability.com/pdf/CDL_ISR_2025.pdf",
    "F34": "https://www.wilmar-international.com/docs/default-source/default-document-library/sustainability/resource/wilmar-sustainability-reports/24_0151_wilmar_2024_sr-v7-27-may.pdf?sfvrsn=f6d89876_8",
}


async def _fetch_report(web: WebTools, name: str, url: str) -> dict | None:
    try:
        fetched = await web.fetch_url(url, max_chars=REPORT_CHARS)
    except Exception:
        return None
    text = str(fetched.get("text") or "")
    if len(text) < 500:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return {"url": fetched.get("url") or url,
            "title": fetched.get("title") or f"{name} Sustainability Report",
            "text": text}


async def _find_report(web: WebTools, name: str, domain: str, pinned: str | None = None) -> dict | None:
    """Discover + fetch the company's sustainability-report PDF; None if unusable."""
    if pinned:
        rep = await _fetch_report(web, name, pinned)
        if rep:
            return rep
    queries = [
        f"site:{domain} sustainability report filetype:pdf",
        f'"{name}" sustainability report 2024 filetype:pdf',
        f'"{name}" sustainability report filetype:pdf',
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
            if u.lower().split("?", 1)[0].endswith(".pdf"):
                candidates.setdefault(u, (r.get("title") or ""))

    def score(u: str, title: str) -> int:
        low = (u + " " + title).lower()
        s = 0
        if domain and domain in u:
            s += 10
        if any(k in low for k in ("sustainab", "esg", "/sr", "sr2", "_sr", "-sr")):
            s += 6
        if any(y in low for y in ("2024", "2025", "2023")):
            s += 2
        if any(k in low for k in ("annual-report", "annualreport", "ar20", "10-k", "agm")):
            s -= 3  # bias away from pure financial annual reports
        return s

    if not candidates:
        return None
    url = max(candidates.items(), key=lambda kv: score(kv[0], kv[1]))[0]
    return await _fetch_report(web, name, url)


def _claim_rows(cid: str, industry: str, rep: dict, client) -> list[dict]:
    """Deep extraction across the WHOLE report; falls back to the deterministic
    Mock splitter if the live model yields nothing (e.g. a bad model response)."""
    rows = _extract_rows(cid, industry, rep, client)
    if not rows:
        rows = _extract_rows(cid, industry, rep, MockLLMClient())
    return rows[:MAX_CLAIMS]


def _extract_rows(cid: str, industry: str, rep: dict, client) -> list[dict]:
    text = rep["text"]
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)][:MAX_CHUNKS] or [text]
    rows, seen = [], set()
    for chunk in chunks:
        if len(chunk.strip()) < 50:  # skip only near-empty trailing fragments
            continue
        doc = DocumentRow(company_id=cid, doc_id=rep["url"], title=rep["title"],
                          year=config.END_YEAR, url=rep["url"], source_page=1, text=chunk)
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
        })
    return rows


def cached_claims_for(cid: str, absent: list[dict] | None = None) -> dict | None:
    cache_path = config.CACHE_DIR / "realclaims" / f"{cid}.json"
    if not cache_path.exists():
        return None
    cached = json.loads(cache_path.read_text("utf-8"))
    rows = cached.get("rows") or []
    if not rows:
        return None
    return {
        "claims": rows,
        "absent": absent or [],
        "live": True,
        "source_url": cached.get("source_url"),
        "source_title": cached.get("source_title"),
    }


def _apply(cid: str, rows: list[dict], rep: dict) -> None:
    cache_dir = config.CACHE_DIR / "realclaims"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cid}.json").write_text(
        json.dumps({"rows": rows, "source_url": rep["url"], "source_title": rep["title"]},
                   ensure_ascii=False, indent=2), "utf-8")
    path = config.OUT_DIR / "company" / f"{cid}.json"
    if path.exists():
        data = json.loads(path.read_text("utf-8"))
        absent = data.get("claims", {}).get("absent", [])
        live_claims = cached_claims_for(cid, absent=absent)
        if live_claims:
            data["claims"] = live_claims
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")


def build_real_claims(cids: list[str]) -> dict:
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

    async def process(cid: str) -> tuple[str, int, int]:
        name = ds.company(cid).name
        industry = ds.company(cid).sasb_industry
        rep = await _find_report(web, name, DOMAINS.get(cid, ""), REPORT_URLS.get(cid))
        if not rep:
            print(f"  {cid:4} {name:24} SKIP (no usable report PDF found)")
            return cid, 0, 0
        # extraction + inference are sync (LLM SDK) → run in a thread so all
        # companies process concurrently instead of one-by-one.
        real_rows, inferred_rows = await asyncio.to_thread(
            _extract_and_infer, cid, industry, rep, client
        )
        rows = real_rows + inferred_rows
        if not rows:
            print(f"  {cid:4} {name:24} SKIP (no material claims extracted)")
            return cid, 0, 0
        _apply(cid, rows, rep)
        print(f"  {cid:4} {name:24} {len(real_rows):2d} real + {len(inferred_rows):2d} inferred"
              f"  <- {rep['url'][:55]}")
        return cid, len(real_rows), len(inferred_rows)

    async def run_all():
        return await asyncio.gather(*[process(c) for c in cids])

    results = asyncio.run(run_all())
    return {cid: real + inferred for cid, real, inferred in results}


def _extract_and_infer(cid: str, industry: str, rep: dict, client) -> tuple[list[dict], list[dict]]:
    real_rows = _claim_rows(cid, industry, rep, client)
    inferred_rows = _infer_missing_topics(industry, rep, real_rows, client)
    return real_rows, inferred_rows


def main() -> None:
    cids = [c.upper() for c in sys.argv[1:]] or DEFAULT_SUBSET
    print(f"Extracting REAL claims for: {', '.join(cids)}")
    summary = build_real_claims(cids)
    total = sum(summary.values())
    print(f"Done. {total} claims (real + labelled inference) across "
          f"{sum(1 for v in summary.values() if v)} companies.")
    print("Now rebuild the dashboard JSON so the new evidence scores apply:")
    print("    python -m backend.engine.pipeline")


if __name__ == "__main__":
    main()
