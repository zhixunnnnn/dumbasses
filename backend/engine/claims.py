"""extract_claims — parse a report into atomic claims with a verbatim source_sentence.

Integrity guard (makes T1 honest): a returned claim is DROPPED unless its
`source_sentence` is a non-empty exact substring of the document text. This kills
hallucinated quotes. Results are cached per (company, year) so `--offline` reuses them.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from . import config
from .ingest import DocumentRow
from .llm import LLMClient, MockLLMClient
from .models import Claim


def _cache_path(company_id: str, year: int):
    d = config.CACHE_DIR / "claims"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{company_id}_{year}.json"


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def extract_claims(doc: DocumentRow, client: Optional[LLMClient] = None,
                   use_cache: bool = True) -> list[Claim]:
    client = client or MockLLMClient()
    cache = _cache_path(doc.company_id, doc.year)
    text_hash = hashlib.sha1(doc.text.encode("utf-8")).hexdigest()
    raw = None
    if use_cache and cache.exists():
        cached = json.loads(cache.read_text("utf-8"))
        if isinstance(cached, dict) and cached.get("_hash") == text_hash:  # invalidate if text changed
            raw = cached.get("claims", [])
    if raw is None:
        raw = client.extract(doc.text)
        if use_cache:
            cache.write_text(json.dumps({"_hash": text_hash, "claims": raw},
                                        ensure_ascii=False, indent=2), "utf-8")

    claims: list[Claim] = []
    seen: set[str] = set()
    for item in raw:
        sentence = (item.get("source_sentence") or "").strip()
        # integrity guard: must be a non-empty verbatim substring of the source text
        if not sentence or sentence not in doc.text:
            continue
        key = _norm(item.get("text") or sentence)
        if key in seen:
            continue
        seen.add(key)
        cid = hashlib.sha1(f"{doc.doc_id}:{key}".encode()).hexdigest()[:12]
        claims.append(Claim(
            id=cid, company_id=doc.company_id, year=doc.year,
            text=(item.get("text") or sentence).strip(),
            source_doc=doc.doc_id, source_page=item.get("source_page") or doc.source_page,
            source_sentence=sentence,
        ))
    return claims
