"""Upgrade cached ASSERTED claims to VERIFIED when an INDEPENDENT source corroborates them.

For each company-disclosed (ASSERTED) topic we SERP for third-party coverage
(news, ratings, CDP, regulators — anything not on the company's own domain), then ask
the model — strictly — whether at least one independent source confirms the claim. If so
the claim becomes VERIFIED and the corroborating link is recorded. This is what powers
real "proof_up" in the Underpriced-Improver signal. One-time + cached.

    python -m backend.data.verifyclaims            # all tracked companies
    python -m backend.data.verifyclaims D05 U11    # specific companies
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from urllib.parse import urlparse

from backend.app.agent import WebTools, load_env
from backend.engine import config, ingest
from backend.engine.llm import OpenRouterLLMClient
from backend.engine.sasb import topics_for
from backend.data.realclaims import DOMAINS, cached_claims_for


# Social media, forums, blogs, wikis, and raw file hosts — not credible named sources.
WEAK_SOURCES = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "reddit.com", "medium.com", "tiktok.com",
    "quora.com", "pinterest.com", "wikipedia.org", "slideshare.net", "scribd.com",
    "blogspot.com", "wordpress.com", "substack.com", "threads.net",
    "amazonaws.com", "cloudfront.net", "googleusercontent.com",
    "blob.core.windows.net", "storage.googleapis.com",
}
# second-level domains that aren't the brand (e.g. channelnewsasia.com.sg -> brand is the 3rd-last)
_SLD = {"com", "org", "gov", "net", "edu", "co", "ac", "go", "or"}


def _is_credible(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return bool(host) and not any(host == w or host.endswith("." + w) for w in WEAK_SOURCES)


def _source_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in _SLD:
        label = parts[-3]          # e.g. straitstimes.com.sg -> straitstimes
    elif len(parts) >= 2:
        label = parts[-2]          # e.g. reuters.com -> reuters
    else:
        label = host
    return label.replace("-", " ").title() or host


async def _corroborate(web, client, name: str, domain: str, claim_text: str, topic: dict) -> dict | None:
    keywords = " ".join(topic.get("keywords", [])[:3])
    try:
        res = await web.search(f'"{name}" {keywords} ESG', max_results=8)
    except Exception:
        return None
    independent = [
        r for r in res.get("results", [])
        if (r.get("url") or "").startswith("http")
        and domain not in (r.get("url") or "")
        and _is_credible(r.get("url") or "")
    ][:5]
    if not independent:
        return None
    listed = "\n".join(
        f'{i}. {r.get("title", "")} — {(r.get("snippet") or "")[:160]} [{r.get("url")}]'
        for i, r in enumerate(independent)
    )
    prompt = (
        f'A company ("{name}") discloses: "{claim_text}"\n\n'
        f"Independent (third-party) search results:\n{listed}\n\n"
        "Decide if at least ONE result is a CREDIBLE INDEPENDENT source that clearly "
        "corroborates the claim. Credible = news outlets/wires, rating agencies "
        "(MSCI, S&P, Sustainalytics, Moody's), regulators or stock exchanges, or "
        "recognised ESG bodies/initiatives (CDP, SBTi, GRI, RSPO, SPOTT, TCFD). "
        "REJECT: the company's own site/PR, social media, blogs, forums, and wikis. "
        "Be STRICT — only true with clear, on-topic support from such a source.\n"
        'Return JSON {"corroborated": true|false, "source_index": <0-based int, -1 if none>, "reason": "..."}.'
    )
    try:
        data = await asyncio.to_thread(client.complete_json, prompt)
    except Exception:
        return None
    if not data.get("corroborated"):
        return None
    idx = data.get("source_index", -1)
    if not isinstance(idx, int) or not (0 <= idx < len(independent)):
        return None
    url = independent[idx].get("url")
    return {"url": url, "source": _source_name(url)}


async def _verify_company(cid: str, ds, web, client) -> tuple[str, int]:
    payload = cached_claims_for(cid)
    if not payload:
        print(f"  {cid:4} {ds.company(cid).name:24} SKIP (no cached claims)")
        return cid, 0
    rows = payload["claims"]
    name = ds.company(cid).name
    domain = DOMAINS.get(cid, "")
    topics_by_id = {t["topic_id"]: t for t in topics_for(ds.company(cid).sasb_industry)}

    # one representative claim per topic (re-evaluate ASSERTED and prior VERIFIED so a
    # re-run with stricter rules also DOWNGRADES weak corroborations).
    reps: dict[str, dict] = {}
    for row in rows:
        if row.get("state") in ("ASSERTED", "VERIFIED") and row["topic_id"] not in reps:
            reps[row["topic_id"]] = row

    upgraded, changed = 0, False
    for tid, row in reps.items():
        topic = topics_by_id.get(tid)
        if not topic:
            continue
        corr = await _corroborate(web, client, name, domain, row["text"], topic)
        if corr:
            if row.get("state") != "VERIFIED" or row.get("corroboration_url") != corr["url"]:
                changed = True
            row["state"] = "VERIFIED"
            row["corroboration_url"] = corr["url"]
            row["corroboration_source"] = corr["source"]
            upgraded += 1
        elif row.get("state") == "VERIFIED":  # previously verified, no longer credible -> downgrade
            row["state"] = "ASSERTED"
            row.pop("corroboration_url", None)
            row.pop("corroboration_source", None)
            changed = True

    if changed:
        _save(cid, rows, payload)
    print(f"  {cid:4} {name:24} {upgraded:2d} topic(s) credibly verified")
    return cid, upgraded


def _save(cid: str, rows: list[dict], payload: dict) -> None:
    cache_dir = config.CACHE_DIR / "realclaims"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cid}.json").write_text(
        json.dumps({"rows": rows, "source_url": payload.get("source_url"),
                    "source_title": payload.get("source_title")}, ensure_ascii=False, indent=2),
        "utf-8",
    )
    out = config.OUT_DIR / "company" / f"{cid}.json"
    if out.exists():
        data = json.loads(out.read_text("utf-8"))
        absent = data.get("claims", {}).get("absent", [])
        data["claims"] = cached_claims_for(cid, absent=absent)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")


def verify_claims(cids: list[str]) -> dict:
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        # Fallback: independent verification needs the judge LLM. Without a key we
        # leave claims as ASSERTED/seeded rather than fabricating VERIFIED badges.
        print("No OPENROUTER_API_KEY — skipping verification (claims stay ASSERTED).")
        return {}
    ds = ingest.load()
    web = WebTools()
    client = OpenRouterLLMClient()

    async def run_all():
        return await asyncio.gather(*[_verify_company(c, ds, web, client) for c in cids])

    return {cid: n for cid, n in asyncio.run(run_all())}


def main() -> None:
    cids = [c.upper() for c in sys.argv[1:]] or list(DOMAINS)
    print(f"Independently verifying claims for: {', '.join(cids)}")
    summary = verify_claims(cids)
    print(f"Done. {sum(summary.values())} topics verified across "
          f"{sum(1 for v in summary.values() if v)} companies.")
    print("Rebuild the dashboard JSON:  python -m backend.engine.pipeline --offline")


if __name__ == "__main__":
    main()
