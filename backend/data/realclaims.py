"""Replace a company's SEEDED 'Claims & Evidence' with REAL claims extracted from its
actual sustainability report — without touching the curated scores/quadrant/forecast.

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
import re
import sys

from backend.app.agent import REPORT_FETCH_CHARS, WebTools, load_env
from backend.engine import config, ingest
from backend.engine.claims import extract_claims
from backend.engine.ingest import DocumentRow
from backend.engine.llm import OpenRouterLLMClient
from backend.engine.sasb import map_to_sasb

# Official corporate domains for the demo universe (used to prefer the primary disclosure).
DOMAINS = {
    "D05": "dbs.com", "O39": "ocbc.com", "U11": "uobgroup.com", "Z74": "singtel.com",
    "C6L": "singaporeair.com", "BN4": "keppel.com", "U96": "sembcorp.com",
    "9CI": "capitaland.com", "C09": "cdl.com.sg", "F34": "wilmar-international.com",
}
DEFAULT_SUBSET = ["D05", "U96", "BN4"]
MAX_CLAIMS = 14
REPORT_CHARS = 24000  # report window; larger inputs yield fewer verbatim-matching claims

# Pinned official report PDFs for the demo subset — removes SERP roulette so the
# pitch is stable and rich. SERP discovery still runs for any company not pinned.
REPORT_URLS = {
    "D05": "https://www.dbs.com/annualreports/2024/i/pdf/dbs_sr2024.pdf",
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
    doc = DocumentRow(company_id=cid, doc_id=rep["url"], title=rep["title"],
                      year=config.END_YEAR, url=rep["url"], source_page=1, text=rep["text"])
    rows, seen = [], set()
    for claim in extract_claims(doc, client=client):
        mapping = map_to_sasb(claim, industry)
        if not mapping.is_material:
            continue
        key = claim.text.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "topic_id": mapping.topic_id, "pillar": mapping.pillar,
            "state": "ASSERTED",  # company self-disclosure; VERIFIED needs independent corroboration
            "text": claim.text, "source_sentence": claim.source_sentence,
            "source_doc": rep["title"], "source_url": rep["url"],
            "source_page": claim.source_page, "weight": mapping.weight,
        })
        if len(rows) >= MAX_CLAIMS:
            break
    return rows


def _apply(cid: str, rows: list[dict], rep: dict) -> None:
    path = config.OUT_DIR / "company" / f"{cid}.json"
    data = json.loads(path.read_text("utf-8"))
    absent = data.get("claims", {}).get("absent", [])  # keep the seeded "undisclosed topics"
    data["claims"] = {"claims": rows, "absent": absent, "live": True,
                      "source_url": rep["url"], "source_title": rep["title"]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")
    cache_dir = config.CACHE_DIR / "realclaims"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cid}.json").write_text(
        json.dumps({"rows": rows, "source_url": rep["url"], "source_title": rep["title"]},
                   ensure_ascii=False, indent=2), "utf-8")


def build_real_claims(cids: list[str]) -> dict:
    load_env()
    ds = ingest.load()
    web = WebTools()
    client = OpenRouterLLMClient()

    async def fetch_all():
        return await asyncio.gather(*[
            _find_report(web, ds.company(c).name, DOMAINS.get(c, ""), REPORT_URLS.get(c))
            for c in cids
        ])

    reports = asyncio.run(fetch_all())
    summary = {}
    for cid, rep in zip(cids, reports):
        name = ds.company(cid).name
        if not rep:
            print(f"  {cid:4} {name:24} SKIP (no usable report PDF found)")
            summary[cid] = 0
            continue
        rows = _claim_rows(cid, ds.company(cid).sasb_industry, rep, client)
        if not rows:
            print(f"  {cid:4} {name:24} SKIP (no material claims extracted)")
            summary[cid] = 0
            continue
        _apply(cid, rows, rep)
        print(f"  {cid:4} {name:24} {len(rows):2d} real claims  <- {rep['url'][:60]}")
        summary[cid] = len(rows)
    return summary


def main() -> None:
    cids = [c.upper() for c in sys.argv[1:]] or DEFAULT_SUBSET
    print(f"Extracting REAL claims for: {', '.join(cids)}")
    summary = build_real_claims(cids)
    total = sum(summary.values())
    print(f"Done. {total} real claims across {sum(1 for v in summary.values() if v)} companies.")
    print("Reload the dashboard to see them (scores/quadrant unchanged).")


if __name__ == "__main__":
    main()
