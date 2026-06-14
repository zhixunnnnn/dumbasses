"""LLM claim extraction behind a swappable interface.

`MockLLMClient` is deterministic (no network) and used for tests and `--offline`.
`OpenAILLMClient` calls OpenAI live when a key is present. Both return raw claim
dicts `{text, source_sentence, source_page?}`; claims.py validates them.
"""
from __future__ import annotations

import os
import re
from typing import Protocol


class LLMClient(Protocol):
    def extract(self, text: str) -> list[dict]:
        ...


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


class MockLLMClient:
    """Deterministic: one sentence = one atomic claim, source_sentence verbatim."""

    name = "mock"

    def extract(self, text: str) -> list[dict]:
        out = []
        for sent in _SENT_SPLIT.split(text.strip()):
            sent = sent.strip()
            if len(sent) < 8:
                continue
            out.append({"text": sent, "source_sentence": sent, "source_page": 1})
        return out


class OpenAILLMClient:
    """Live extraction via OpenAI. source_sentence must be copied verbatim from the text."""

    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI  # imported lazily so offline never needs the package configured

        self.client = OpenAI()
        self.model = model

    def extract(self, text: str) -> list[dict]:
        import json

        prompt = (
            "Extract atomic ESG claims from the sustainability-report excerpt. "
            "One statement = one claim. For each, copy the EXACT verbatim sentence "
            "from the text into `source_sentence` (do not paraphrase). "
            "Return JSON: {\"claims\":[{\"text\":...,\"source_sentence\":...,\"source_page\":1}]}.\n\n"
            f"EXCERPT:\n{text}"
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return data.get("claims", [])


def get_default_client(offline: bool = True) -> LLMClient:
    """Offline or no key -> deterministic mock. Online + key -> live OpenAI."""
    if not offline and os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAILLMClient()
        except Exception:
            return MockLLMClient()
    return MockLLMClient()
