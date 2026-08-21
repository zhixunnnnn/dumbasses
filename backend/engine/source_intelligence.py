"""Persistent ESG research, source trust, corroboration, and provenance.

This module deliberately keeps source reputation separate from claim
verification. A promoted domain is eligible to be treated as verified, but a
claim still needs relevant text and an independent source record.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from . import config
from .db import bootstrap
from .scrape_settings import enabled_providers, get_scrape_settings


SOURCE_CONFIG = Path(config.CONFIG_DIR) / "source_registry.json"
TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source",
}
ESG_TERMS = {
    "sustainability", "esg", "emission", "emissions", "carbon", "climate",
    "renewable", "solar", "wind", "energy", "governance", "workforce",
    "diversity", "labour", "labor", "supply chain", "water", "waste",
    "biodiversity", "net zero", "green finance", "transition",
}
RENEWABLE_TERMS = {
    "renewable energy", "renewable electricity", "solar energy", "solar power",
    "wind power", "green electricity", "clean energy", "power purchase agreement",
    "ppa", "recs", "renewable energy certificate",
}
POSITIVE_USE_TERMS = {
    "uses", "using", "use of", "powered by", "procures", "procured", "purchased",
    "generates", "generated", "installed", "adopted", "transitioned", "sources",
    "consumption", "electricity from",
}
FALLING_TERMS = {"reduced", "reduction", "declined", "decreased", "fell", "lowered", "down"}
RISING_TERMS = {"increased", "increase", "rose", "rising", "grew", "higher", "up"}
COMMUNITY_WEIGHT = 0.02
# Registering one of these would silently classify every commercial site beneath
# it. Institution-scoped suffixes (gov.sg, ac.uk) are deliberately absent: the
# builtin registry whitelists gov.sg wholesale and that is a reasonable thing to
# want, so only the generic ones are refused.
PUBLIC_SUFFIXES = {
    "com", "net", "org", "edu", "gov", "int", "mil", "io", "co", "ai", "app", "dev",
    "sg", "com.sg", "net.sg", "org.sg", "per.sg",
    "uk", "co.uk", "org.uk",
    "au", "com.au", "net.au", "org.au",
    "jp", "co.jp", "or.jp", "cn", "com.cn",
    "my", "com.my", "hk", "com.hk", "id", "co.id", "in", "co.in",
}


class ResearchWebTools(Protocol):
    async def search(self, query: str, max_results: int = 25) -> dict[str, Any]: ...
    async def fetch_url(self, url: str, max_chars: int = 18000) -> dict[str, Any]: ...


@dataclass
class Candidate:
    company_id: str
    title: str
    url: str
    snippet: str
    provider: str
    domain: str
    source_class: str


@dataclass
class ClaimCandidate:
    company_id: str
    text: str
    topic: str
    sentiment: float
    source: Candidate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=False)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
        )
    )
    return urlunparse((parsed.scheme.lower(), host + port, path, "", query, ""))


def domain_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def normalize_domain(value: str) -> str:
    """Reduce user input to the host it registers against.

    Accepts a bare domain or a full URL and keeps only the hostname, so
    `https://www.reuters.com/business/energy/x-2026` and `reuters.com` register
    the same entry. A registered host also covers its subdomains via
    `classify_domain`, so a path or query would only ever narrow it wrongly.
    """
    raw = (value or "").strip().lower()
    if not raw:
        raise ValueError("Enter a domain.")
    host = (urlparse(raw if "://" in raw else f"//{raw}").hostname or "").strip(".")
    host = host.removeprefix("www.")
    if not host or "." not in host:
        raise ValueError(f"{value!r} is not a domain (expected something like example.com).")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
        raise ValueError(f"{value!r} is not a valid domain.")
    if host in PUBLIC_SUFFIXES:
        raise ValueError(f"{host!r} is a public suffix; it would match every site under it.")
    return host


def source_registry_config() -> dict[str, Any]:
    return json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))


def initialize_source_registry() -> None:
    registry = source_registry_config()
    now = utc_now()
    conn = bootstrap()
    try:
        for domain, reason in registry.get("verified_domains", {}).items():
            conn.execute(
                """
                INSERT INTO source_registry(domain, source_class, reason, is_builtin, updated_at)
                VALUES (?, 'verified', ?, 1, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    reason=CASE WHEN user_modified=1 THEN reason ELSE excluded.reason END,
                    is_builtin=1
                """,
                (normalize_domain(domain), reason, now),
            )
        for domain, reason in registry.get("community_domains", {}).items():
            conn.execute(
                """
                INSERT INTO source_registry(domain, source_class, reason, is_builtin, updated_at)
                VALUES (?, 'community', ?, 1, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    reason=CASE WHEN user_modified=1 THEN reason ELSE excluded.reason END,
                    is_builtin=1
                """,
                (normalize_domain(domain), reason, now),
            )
        conn.commit()
    finally:
        conn.close()


def classify_domain(domain: str, conn=None) -> str:
    own = conn is None
    conn = conn or bootstrap()
    try:
        labels = conn.execute(
            "SELECT domain, source_class FROM source_registry WHERE is_disabled=0"
        ).fetchall()
        domain = domain.lower().removeprefix("www.")
        best: tuple[int, str] | None = None
        for row in labels:
            registered = row["domain"]
            if domain == registered or domain.endswith(f".{registered}"):
                if best is None or len(registered) > best[0]:
                    best = (len(registered), row["source_class"])
        return best[1] if best else "non_verified"
    finally:
        if own:
            conn.close()


def list_source_registry() -> dict[str, Any]:
    initialize_source_registry()
    conn = bootstrap()
    try:
        sources = [dict(row) for row in conn.execute(
            "SELECT domain, source_class, reason, is_builtin, updated_at "
            "FROM source_registry WHERE is_disabled=0 ORDER BY source_class, domain"
        )]
        candidates = [dict(row) for row in conn.execute(
            """
            SELECT domain, status, overlap_score, matching_claims,
                   matched_verified_domains, first_seen, last_seen, reviewed_at
            FROM source_promotion_candidates
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                     overlap_score DESC, last_seen DESC
            """
        )]
        for item in candidates:
            item["matched_verified_domains"] = json.loads(item["matched_verified_domains"])
        observed = [dict(row) for row in conn.execute(
            """
            SELECT domain, COUNT(*) AS pages, MAX(fetched_at) AS last_fetched
            FROM scraped_pages
            WHERE source_class = 'non_verified'
            GROUP BY domain
            ORDER BY pages DESC, domain
            LIMIT 200
            """
        )]
        return {"sources": sources, "candidates": candidates, "observed": observed}
    finally:
        conn.close()


SOURCE_CLASSES = {"verified", "non_verified", "community"}


def upsert_source_domain(domain: str, source_class: str, reason: str | None = None) -> dict[str, Any]:
    """Add a domain or change the class/reason of an existing one."""
    if source_class not in SOURCE_CLASSES:
        raise ValueError(f"source_class must be one of {sorted(SOURCE_CLASSES)}.")
    domain = normalize_domain(domain)
    reason = (reason or "").strip() or None
    initialize_source_registry()
    now = utc_now()
    conn = bootstrap()
    try:
        conn.execute(
            """
            INSERT INTO source_registry(
                domain, source_class, reason, is_builtin, is_disabled, user_modified, updated_at)
            VALUES (?, ?, ?, 0, 0, 1, ?)
            ON CONFLICT(domain) DO UPDATE SET
                source_class=excluded.source_class,
                reason=excluded.reason,
                is_disabled=0,
                user_modified=1,
                updated_at=excluded.updated_at
            """,
            (domain, source_class, reason, now),
        )
        conn.commit()
    finally:
        conn.close()
    return list_source_registry()


def delete_source_domain(domain: str) -> dict[str, Any]:
    """Remove a domain. Builtins are disabled instead, since the seed re-adds them."""
    domain = normalize_domain(domain)
    initialize_source_registry()
    now = utc_now()
    conn = bootstrap()
    try:
        row = conn.execute(
            "SELECT is_builtin FROM source_registry WHERE domain=? AND is_disabled=0", (domain,)
        ).fetchone()
        if not row:
            raise KeyError(domain)
        if row["is_builtin"]:
            conn.execute(
                "UPDATE source_registry SET is_disabled=1, user_modified=1, updated_at=? "
                "WHERE domain=?",
                (now, domain),
            )
        else:
            conn.execute("DELETE FROM source_registry WHERE domain=?", (domain,))
        conn.commit()
    finally:
        conn.close()
    return list_source_registry()


def review_source_candidate(domain: str, decision: str) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    initialize_source_registry()
    domain = domain.lower().removeprefix("www.").strip()
    now = utc_now()
    conn = bootstrap()
    try:
        row = conn.execute(
            "SELECT * FROM source_promotion_candidates WHERE domain=?", (domain,)
        ).fetchone()
        if not row:
            raise KeyError(domain)
        conn.execute(
            "UPDATE source_promotion_candidates SET status=?, reviewed_at=? WHERE domain=?",
            (decision, now, domain),
        )
        if decision == "approved":
            conn.execute(
                """
                INSERT INTO source_registry(domain, source_class, reason, is_builtin, updated_at)
                VALUES (?, 'verified', ?, 0, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    source_class='verified', reason=excluded.reason,
                    is_builtin=0, updated_at=excluded.updated_at
                """,
                (domain, "Manually promoted after cross-reference review", now),
            )
        conn.commit()
    finally:
        conn.close()
    return list_source_registry()


def get_research_status() -> dict[str, Any]:
    conn = bootstrap()
    try:
        row = conn.execute(
            "SELECT * FROM research_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else {"status": "never_run"}
    finally:
        conn.close()


def get_company_intelligence(company_id: str) -> dict[str, Any]:
    conn = bootstrap()
    try:
        company = conn.execute(
            "SELECT company_id, name, ticker FROM universe WHERE company_id=?",
            (company_id,),
        ).fetchone()
        if not company:
            raise KeyError(company_id)
        renewable = conn.execute(
            "SELECT * FROM renewable_status WHERE company_id=?", (company_id,)
        ).fetchone()
        claims = [dict(row) for row in conn.execute(
            """
            SELECT claim_id, claim_text, topic, verification, sentiment, last_seen
            FROM research_claims WHERE company_id=?
            ORDER BY CASE verification WHEN 'verified' THEN 0 WHEN 'non_verified' THEN 1 ELSE 2 END,
                     last_seen DESC
            """,
            (company_id,),
        )]
        for claim in claims:
            claim["sources"] = [dict(row) for row in conn.execute(
                """
                SELECT canonical_url AS url, domain, source_class, title, snippet, provider, fetched_at
                FROM research_claim_sources WHERE claim_id=? ORDER BY source_class, domain
                """,
                (claim["claim_id"],),
            )]
        community = [claim for claim in claims if claim["verification"] == "community"]
        community_signal = sum(float(claim["sentiment"]) for claim in community)
        community_signal = max(-2.0, min(2.0, community_signal * COMMUNITY_WEIGHT * 100))
        # "No evidence found" is ambiguous on a renewables developer: we may have found
        # plenty of renewable coverage that simply never evidences the company's OWN
        # consumption (buying a solar farm is not running on solar). Count the mentions
        # so the UI can say "found, but none evidencing use" instead of implying a gap.
        renewable_mentions = sum(1 for claim in claims if claim["topic"] == "renewable_energy")
        renewable_block = dict(renewable) if renewable else {
            "company_id": company_id,
            "renewable_status": "No evidence found",
            "emissions_trend": "No evidence found",
            "evidence_count": 0,
            "verified_count": 0,
            "latest_evidence_at": None,
        }
        renewable_block["renewable_mentions"] = renewable_mentions
        return {
            "company": dict(company),
            "renewable": renewable_block,
            "claims": claims,
            "community_sentiment_adjustment": round(community_signal, 2),
            "community_sentiment_note": "Applied only to the live news/LLM signal; never to core evidence verification.",
        }
    finally:
        conn.close()


async def run_research(
    web_tools: ResearchWebTools,
    company_id: str | None = None,
    force: bool = True,
) -> dict[str, Any]:
    initialize_source_registry()
    settings = get_scrape_settings()
    providers = enabled_providers()
    conn = bootstrap()
    try:
        if company_id:
            companies = conn.execute(
                "SELECT company_id, name, ticker FROM universe WHERE company_id=? AND scope='demo'",
                (company_id,),
            ).fetchall()
        else:
            companies = conn.execute(
                "SELECT company_id, name, ticker FROM universe WHERE scope='demo' "
                "ORDER BY company_id LIMIT ?",
                (int(settings["maxCompanies"]),),
            ).fetchall()
        if not companies:
            raise KeyError(company_id or "demo universe")
    finally:
        conn.close()

    run_id = str(uuid.uuid4())
    started = utc_now()
    _insert_run(run_id, company_id, providers, started)
    totals = {"sources": 0, "claims": 0, "errors": []}
    try:
        for company in companies:
            result = await research_company(
                web_tools,
                dict(company),
                settings=settings,
            )
            totals["sources"] += result["source_count"]
            totals["claims"] += result["claim_count"]
            totals["errors"].extend(result["errors"])
        _finish_run(run_id, "complete", totals)
    except Exception as exc:
        totals["errors"].append(f"{type(exc).__name__}: {str(exc)[:300]}")
        _finish_run(run_id, "failed", totals)
        raise
    return {"run_id": run_id, "status": "complete", **totals}


async def research_company(
    web_tools: ResearchWebTools,
    company: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_scrape_settings()
    source_types = settings.get("sourceTypes", {
        "verified": True, "nonVerified": True, "community": True,
    })
    queries = company_queries(company["name"], company.get("ticker"))
    candidates: dict[str, Candidate] = {}
    errors: list[str] = []
    stale_rounds = 0

    for query in queries:
        before = len(candidates)
        try:
            result = await web_tools.search(query, max_results=25)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {str(exc)[:160]}")
            stale_rounds += 1
            if stale_rounds >= 2 and candidates:
                break
            continue
        for item in result.get("results", []):
            url = canonicalize_url(str(item.get("url") or ""))
            if not url or url in candidates:
                continue
            domain = domain_from_url(url)
            source_class = classify_domain(domain)
            if source_class == "verified" and not source_types.get("verified", True):
                continue
            if source_class == "non_verified" and not source_types.get("nonVerified", True):
                continue
            if source_class == "community" and not source_types.get("community", True):
                continue
            text = f"{item.get('title') or ''} {item.get('snippet') or ''}"
            if not relevant_to_company(text, company):
                continue
            candidates[url] = Candidate(
                company_id=company["company_id"],
                title=str(item.get("title") or url)[:300],
                url=url,
                snippet=str(item.get("snippet") or "")[:1000],
                provider=str(item.get("source") or result.get("source") or "search"),
                domain=domain,
                source_class=source_class,
            )
        added = len(candidates) - before
        stale_rounds = stale_rounds + 1 if added == 0 else 0
        if stale_rounds >= 2 and candidates:
            break

    pages = await _fetch_candidates(web_tools, list(candidates.values()), settings, errors)
    raw_claims: list[ClaimCandidate] = []
    for candidate, text in pages:
        raw_claims.extend(extract_claims(candidate, text, company))
    grouped = group_claims(raw_claims)
    persist_company_research(company["company_id"], pages, grouped, settings)
    return {
        "company_id": company["company_id"],
        "source_count": len(pages),
        "claim_count": len(grouped),
        "errors": errors,
    }


async def _fetch_candidates(
    web_tools: ResearchWebTools,
    candidates: list[Candidate],
    settings: dict[str, Any],
    errors: list[str],
) -> list[tuple[Candidate, str]]:
    semaphore = asyncio.Semaphore(6)

    async def fetch(candidate: Candidate) -> tuple[Candidate, str] | None:
        async with semaphore:
            try:
                page = await web_tools.fetch_url(candidate.url, max_chars=18000)
                text = str(page.get("text") or candidate.snippet)
                candidate.provider = str(page.get("source") or candidate.provider)
                candidate.title = str(page.get("title") or candidate.title)[:300]
                return candidate, text
            except Exception as exc:
                if candidate.snippet:
                    return candidate, candidate.snippet
                errors.append(f"{candidate.url}: {type(exc).__name__}")
                return None

    fetched = await asyncio.gather(*(fetch(item) for item in candidates))
    return [item for item in fetched if item is not None]


def company_queries(name: str, ticker: str | None) -> list[str]:
    subject = f'"{name}" {ticker or ""}'.strip()
    return [
        f"{subject} sustainability report ESG climate renewable energy emissions",
        f"{subject} ESG news controversy governance workforce supply chain",
        f"{subject} renewable electricity solar power purchase agreement",
        f"{subject} scope 1 scope 2 scope 3 emissions reduction",
        f"{subject} sustainability target progress 2025 2026",
        f"site:reddit.com {subject} sustainability ESG",
    ]


def relevant_to_company(text: str, company: dict[str, Any]) -> bool:
    value = normalize(text)
    aliases = {
        normalize(company["name"]),
        normalize(company.get("ticker") or ""),
        normalize(company["company_id"]),
    }
    aliases.discard("")
    return any(alias in value for alias in aliases) and any(term in value for term in ESG_TERMS)


def extract_claims(candidate: Candidate, text: str, company: dict[str, Any]) -> list[ClaimCandidate]:
    clean = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+|\s+[|]\s+", clean)
    output: list[ClaimCandidate] = []
    for sentence in sentences:
        sentence = sentence.strip(" -|\t")
        if len(sentence) < 45 or len(sentence) > 600:
            continue
        if not relevant_to_company(sentence, company):
            continue
        topic = classify_topic(sentence)
        output.append(ClaimCandidate(
            company_id=company["company_id"],
            text=sentence[:600],
            topic=topic,
            sentiment=sentiment_score(sentence),
            source=candidate,
        ))
        if len(output) >= 4:
            break
    if not output and candidate.snippet and relevant_to_company(candidate.snippet, company):
        output.append(ClaimCandidate(
            company_id=company["company_id"],
            text=candidate.snippet[:600],
            topic=classify_topic(candidate.snippet),
            sentiment=sentiment_score(candidate.snippet),
            source=candidate,
        ))
    return output


def classify_topic(text: str) -> str:
    value = normalize(text)
    if any(term in value for term in RENEWABLE_TERMS):
        return "renewable_energy"
    if "emission" in value or "carbon" in value or "net zero" in value:
        return "emissions"
    if any(term in value for term in {"governance", "board", "bribery", "corruption"}):
        return "governance"
    if any(term in value for term in {"workforce", "diversity", "labour", "labor", "employee"}):
        return "workforce"
    if any(term in value for term in {"supply chain", "supplier", "deforestation"}):
        return "supply_chain"
    return "general_esg"


def sentiment_score(text: str) -> float:
    value = normalize(text)
    positive = sum(word in value for word in {
        "improved", "reduced", "progress", "achieved", "leader", "award", "increase renewable",
    })
    negative = sum(word in value for word in {
        "controversy", "lawsuit", "breach", "greenwashing", "failed", "pollution", "increased emissions",
    })
    return float(max(-1, min(1, positive - negative)))


def group_claims(claims: list[ClaimCandidate]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for claim in claims:
        tokens = claim_tokens(claim.text)
        match = None
        best = 0.0
        for group in groups:
            if group["topic"] != claim.topic:
                continue
            score = jaccard(tokens, group["tokens"])
            if score > best and score >= 0.46:
                best = score
                match = group
        if match is None:
            groups.append({
                "company_id": claim.company_id,
                "text": claim.text,
                "topic": claim.topic,
                "tokens": tokens,
                "sources": [claim.source],
                "sentiments": [claim.sentiment],
            })
        else:
            if claim.source.url not in {item.url for item in match["sources"]}:
                match["sources"].append(claim.source)
            match["sentiments"].append(claim.sentiment)
            match["tokens"] |= tokens
            if len(claim.text) > len(match["text"]):
                match["text"] = claim.text

    output: list[dict[str, Any]] = []
    for group in groups:
        classes = {item.source_class for item in group["sources"]}
        verification = (
            "verified" if "verified" in classes
            else "community" if classes == {"community"}
            else "non_verified"
        )
        domains = {item.domain for item in group["sources"]}
        digest = hashlib.sha256(
            f"{group['company_id']}|{group['topic']}|{' '.join(sorted(group['tokens']))}".encode("utf-8")
        ).hexdigest()[:24]
        output.append({
            "claim_id": digest,
            "company_id": group["company_id"],
            "claim_text": group["text"],
            "topic": group["topic"],
            "verification": verification,
            "sentiment": sum(group["sentiments"]) / max(1, len(group["sentiments"])),
            "sources": group["sources"],
            "independent_domains": len(domains),
        })
    return output


def persist_company_research(
    company_id: str,
    pages: list[tuple[Candidate, str]],
    claims: list[dict[str, Any]],
    settings: dict[str, Any],
) -> None:
    now = utc_now()
    expires = (datetime.now(timezone.utc) + timedelta(days=int(settings.get("retainRawDays", 30)))).isoformat()
    conn = bootstrap()
    try:
        conn.execute("DELETE FROM scraped_pages WHERE expires_at < ?", (now,))
        for candidate, text in pages:
            conn.execute(
                """
                INSERT INTO scraped_pages(url_hash, canonical_url, domain, provider, title,
                                          extracted_text, source_class, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url_hash) DO UPDATE SET
                    provider=excluded.provider, title=excluded.title,
                    extracted_text=excluded.extracted_text, source_class=excluded.source_class,
                    fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                """,
                (
                    hashlib.sha256(candidate.url.encode("utf-8")).hexdigest(), candidate.url,
                    candidate.domain, candidate.provider, candidate.title, text[:20000],
                    candidate.source_class, now, expires,
                ),
            )
        for claim in claims:
            conn.execute(
                """
                INSERT INTO research_claims(claim_id, company_id, claim_text, topic,
                                            verification, sentiment, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    claim_text=excluded.claim_text, verification=excluded.verification,
                    sentiment=excluded.sentiment, last_seen=excluded.last_seen
                """,
                (
                    claim["claim_id"], company_id, claim["claim_text"], claim["topic"],
                    claim["verification"], claim["sentiment"], now, now,
                ),
            )
            for source in claim["sources"]:
                conn.execute(
                    """
                    INSERT INTO research_claim_sources(claim_id, canonical_url, domain, source_class,
                                                       title, snippet, provider, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(claim_id, canonical_url) DO UPDATE SET
                        source_class=excluded.source_class, title=excluded.title,
                        snippet=excluded.snippet, provider=excluded.provider,
                        fetched_at=excluded.fetched_at
                    """,
                    (
                        claim["claim_id"], source.url, source.domain, source.source_class,
                        source.title, source.snippet, source.provider, now,
                    ),
                )
        _refresh_promotions(conn, claims, now)
        _update_renewable(conn, company_id, claims, now)
        conn.commit()
    finally:
        conn.close()


def _refresh_promotions(conn, claims: list[dict[str, Any]], now: str) -> None:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "claims": 0, "scores": [], "verified_domains": set(),
    })
    for claim in claims:
        verified = {source.domain for source in claim["sources"] if source.source_class == "verified"}
        non_verified = {source.domain for source in claim["sources"] if source.source_class == "non_verified"}
        if not verified:
            continue
        for domain in non_verified:
            stats[domain]["claims"] += 1
            stats[domain]["scores"].append(min(1.0, 0.5 + 0.1 * len(verified)))
            stats[domain]["verified_domains"].update(verified)
    for domain, stat in stats.items():
        if stat["claims"] < 2 or len(stat["verified_domains"]) < 2:
            continue
        overlap = sum(stat["scores"]) / len(stat["scores"])
        conn.execute(
            """
            INSERT INTO source_promotion_candidates(
                domain, status, overlap_score, matching_claims,
                matched_verified_domains, first_seen, last_seen
            ) VALUES (?, 'pending', ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                overlap_score=MAX(source_promotion_candidates.overlap_score, excluded.overlap_score),
                matching_claims=MAX(source_promotion_candidates.matching_claims, excluded.matching_claims),
                matched_verified_domains=excluded.matched_verified_domains,
                last_seen=excluded.last_seen,
                status=CASE WHEN source_promotion_candidates.status='rejected'
                            THEN 'rejected' ELSE source_promotion_candidates.status END
            """,
            (domain, overlap, stat["claims"], json.dumps(sorted(stat["verified_domains"])), now, now),
        )


def _update_renewable(conn, company_id: str, claims: list[dict[str, Any]], now: str) -> None:
    renewable = [claim for claim in claims if claim["topic"] == "renewable_energy" and renewable_use_claim(claim["claim_text"])]
    verified = [claim for claim in renewable if claim["verification"] == "verified"]
    status = "Verified" if verified else "Non-verified" if renewable else "No evidence found"
    emission_claims = [claim for claim in claims if claim["topic"] == "emissions"]
    falling = sum(has_phrase(claim["claim_text"], FALLING_TERMS) for claim in emission_claims)
    rising = sum(has_phrase(claim["claim_text"], RISING_TERMS) for claim in emission_claims)
    trend = "Falling" if falling > rising else "Rising" if rising > falling else "Stable" if emission_claims else "No evidence found"
    conn.execute(
        """
        INSERT INTO renewable_status(company_id, renewable_status, emissions_trend,
                                     evidence_count, verified_count, latest_evidence_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            renewable_status=excluded.renewable_status,
            emissions_trend=excluded.emissions_trend,
            evidence_count=excluded.evidence_count,
            verified_count=excluded.verified_count,
            latest_evidence_at=excluded.latest_evidence_at,
            updated_at=excluded.updated_at
        """,
        (company_id, status, trend, len(renewable), len(verified), now if renewable else None, now),
    )


def renewable_use_claim(text: str) -> bool:
    value = normalize(text)
    return any(term in value for term in RENEWABLE_TERMS) and any(term in value for term in POSITIVE_USE_TERMS)


def has_phrase(value: str, phrases: set[str]) -> bool:
    normalized = normalize(value)
    return any(
        re.search(rf"\b{re.escape(phrase).replace(r'\ ', r'\s+')}\b", normalized)
        for phrase in phrases
    )


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", value.lower()).strip()


def claim_tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "its", "has", "have", "were", "was", "are", "into", "company"}
    return {token for token in normalize(value).split() if len(token) > 2 and token not in stop}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _insert_run(run_id: str, company_id: str | None, providers: list[str], started: str) -> None:
    conn = bootstrap()
    try:
        conn.execute(
            """
            INSERT INTO research_runs(run_id, scope, company_id, status, providers_json, started_at)
            VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (run_id, "company" if company_id else "universe", company_id, json.dumps(providers), started),
        )
        conn.commit()
    finally:
        conn.close()


def _finish_run(run_id: str, status: str, totals: dict[str, Any]) -> None:
    conn = bootstrap()
    try:
        conn.execute(
            """
            UPDATE research_runs SET status=?, finished_at=?, source_count=?, claim_count=?,
                                     error_count=?, message=? WHERE run_id=?
            """,
            (
                status, utc_now(), totals["sources"], totals["claims"], len(totals["errors"]),
                "; ".join(totals["errors"][:5]) or None, run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
