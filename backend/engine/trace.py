"""TraceNode helpers — the product's spine. Every surfaced number must resolve,
through its trace, to at least one non-empty source_sentence (T1)."""
from __future__ import annotations

from typing import Iterator

from .models import TraceNode


def iter_sentences(node: TraceNode) -> Iterator[str]:
    if node.source_sentence:
        yield node.source_sentence
    for child in node.children:
        yield from iter_sentences(child)


def has_source(node: TraceNode) -> bool:
    """True iff the subtree contains at least one non-empty source_sentence."""
    return any(s.strip() for s in iter_sentences(node))


def leaf(label: str, sentence: str, *, doc: str | None = None, page: int | None = None,
         value: float | None = None, contribution: float | None = None) -> TraceNode:
    return TraceNode(label=label, source_sentence=sentence, source_doc=doc,
                     source_page=page, value=value, contribution=contribution)
