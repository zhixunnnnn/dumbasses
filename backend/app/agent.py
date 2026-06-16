from __future__ import annotations

import asyncio
import json
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Literal
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from fastapi import HTTPException
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain.tools import tool
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, ConfigDict, Field


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"
BRIGHT_DATA_FALLBACK_STATUSES = {401, 402, 403, 429}
WORKFLOW_EVENT_QUEUE: ContextVar[asyncio.Queue[Any] | None] = ContextVar(
    "workflow_event_queue",
    default=None,
)


def load_env() -> None:
    for path in (ROOT / ".env", ROOT / "backend" / ".env"):
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env()


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ChatMessage(ApiModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantRequest(ApiModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    page_context: dict[str, Any] = Field(default_factory=dict, alias="pageContext")
    session_id: str | None = Field(default=None, alias="sessionId")


class AssistantSource(ApiModel):
    title: str
    url: str
    snippet: str | None = None
    source: str


class ReferenceArticle(ApiModel):
    title: str
    url: str
    snippet: str | None = None
    source: str
    kind: str = "article"
    reason: str | None = None


class ToolResult(ApiModel):
    name: str
    status: Literal["ok", "error"]
    summary: str
    source_count: int = Field(default=0, alias="sourceCount")


class WorkflowStep(ApiModel):
    label: str
    status: Literal["ok", "error", "running"]
    detail: str
    tool_name: str | None = Field(default=None, alias="toolName")


def emit_workflow_step(
    label: str,
    status: Literal["ok", "error", "running"],
    detail: str,
    tool_name: str | None = None,
) -> None:
    queue = WORKFLOW_EVENT_QUEUE.get()
    if queue is None:
        return
    queue.put_nowait(
        WorkflowStep(
            label=label,
            status=status,
            detail=detail,
            tool_name=tool_name,
        )
    )


class ReportArtifact(ApiModel):
    title: str
    markdown: str
    generated_at: str = Field(alias="generatedAt")


class AssistantResponse(ApiModel):
    message: ChatMessage
    sources: list[AssistantSource] = Field(default_factory=list)
    reference_articles: list[ReferenceArticle] = Field(
        default_factory=list,
        alias="referenceArticles",
    )
    tool_results: list[ToolResult] = Field(default_factory=list, alias="toolResults")
    workflow_steps: list[WorkflowStep] = Field(default_factory=list, alias="workflowSteps")
    report: ReportArtifact | None = None
    model: str


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip_depth += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", " ".join(self.parts)).strip()


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[AssistantSource] = []
        self.current_href: str | None = None
        self.current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self.current_href = urljoin(self.base_url, href)
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.current_href:
            return
        title = " ".join(self.current_text).strip()
        if title and len(title) > 8:
            self.links.append(
                AssistantSource(
                    title=title[:160],
                    url=self.current_href,
                    snippet=None,
                    source="search",
                ),
            )
        self.current_href = None
        self.current_text = []


def extract_text(html: str, max_chars: int = 8000) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.text()[:max_chars]


# Reports (PDFs, long HTML disclosures) need a much larger window than news pages.
DEFAULT_FETCH_CHARS = 8000
REPORT_FETCH_CHARS = 24000


def looks_like_pdf(url: str, content_type: str | None, content: bytes | None) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return True
    if content_type and "application/pdf" in content_type.lower():
        return True
    if content and content[:5] == b"%PDF-":
        return True
    return False


def extract_pdf_text(data: bytes, max_chars: int = REPORT_FETCH_CHARS) -> str:
    """Extract readable text from PDF bytes. Tries PyMuPDF, then pypdf."""
    text = _extract_pdf_pymupdf(data, max_chars) or _extract_pdf_pypdf(data, max_chars)
    if not text:
        return ""
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:max_chars]


def _extract_pdf_pymupdf(data: bytes, max_chars: int) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    parts: list[str] = []
    total = 0
    try:
        for page in doc:
            page_text = page.get_text("text") or ""
            if not page_text.strip():
                continue
            parts.append(page_text)
            total += len(page_text)
            if total >= max_chars:
                break
    except Exception:
        return "\n".join(parts)
    finally:
        doc.close()
    return "\n".join(parts)


def _extract_pdf_pypdf(data: bytes, max_chars: int) -> str:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return ""
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            continue
        if not page_text.strip():
            continue
        parts.append(page_text)
        total += len(page_text)
        if total >= max_chars:
            break
    return "\n".join(parts)


def extract_links(html: str, base_url: str, max_results: int) -> list[AssistantSource]:
    parser = LinkExtractor(base_url)
    parser.feed(html)
    seen: set[str] = set()
    out: list[AssistantSource] = []
    for link in parser.links:
        normalized_url = normalize_search_url(link.url)
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if any(host in parsed.netloc for host in ("duckduckgo.com", "bing.com")):
            continue
        key = normalized_url.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        link.url = normalized_url
        out.append(link)
        if len(out) >= max_results:
            break
    return out


def normalize_search_url(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "uddg" in params and params["uddg"]:
        return unquote(params["uddg"][0])
    return url


def require_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only absolute http(s) URLs can be scraped.")
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local"):
        raise ValueError("Local/private URLs are not available to the web tool.")
    return url


def env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def env_all(*names: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for name in names:
        value = os.environ.get(name)
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def safe_error_summary(exc: Exception, max_chars: int = 240) -> str:
    message = re.sub(r"\s+", " ", str(exc)).strip()
    if not message:
        message = exc.__class__.__name__
    return message[:max_chars]


class WebTools:
    def __init__(self) -> None:
        self.bright_data_keys = env_all(
            "BRIGHTDATA_API_KEY",
            "BRIGHT_DATA_API_KEY",
            "BRIGHTDATA_TOKEN",
            "BRIGHT_DATA_TOKEN",
            "BRIGHTDATA_API_KEY_FALLBACK",
            "BRIGHT_DATA_API_KEY_FALLBACK",
            "BRIGHTDATA_FALLBACK_API_KEY",
            "BRIGHT_DATA_FALLBACK_API_KEY",
            "BRIGHTDATA_TOKEN_FALLBACK",
            "BRIGHT_DATA_TOKEN_FALLBACK",
        )
        self.bright_data_key = self.bright_data_keys[0] if self.bright_data_keys else None
        self.bright_data_zone = env_first(
            "BRIGHTDATA_ZONE",
            "BRIGHT_DATA_ZONE",
            "BRIGHTDATA_WEB_UNLOCKER_ZONE",
            "BRIGHT_DATA_WEB_UNLOCKER_ZONE",
        ) or ("web_unlocker1" if self.bright_data_keys else None)
        # Dedicated Bright Data SERP zone gives clean, structured search results
        # (Google with brd_json=1) for far better discovery/coverage than scraping
        # a DuckDuckGo HTML page. Falls back to the unlocker zone, then DuckDuckGo.
        self.bright_data_serp_zone = env_first(
            "BRIGHTDATA_SERP_ZONE",
            "BRIGHT_DATA_SERP_ZONE",
        ) or ("serp_api1" if self.bright_data_keys else None)

    async def fetch_url(
        self,
        url: str,
        max_chars: int = DEFAULT_FETCH_CHARS,
    ) -> dict[str, Any]:
        raw = await self._fetch_raw(url)
        if looks_like_pdf(raw["url"], raw.get("content_type"), raw.get("content")):
            text = extract_pdf_text(raw["content"], max_chars=max(max_chars, REPORT_FETCH_CHARS))
            return {
                "url": raw["url"],
                "source": f"{raw['source']}+pdf",
                "text": text,
                "title": pdf_title_from_url(raw["url"]),
                "content_type": "application/pdf",
            }
        html = raw["text"]
        return {
            "url": raw["url"],
            "source": raw["source"],
            "text": extract_text(html, max_chars=max_chars),
            "title": title_from_html(html) or raw["url"],
            "content_type": raw.get("content_type") or "text/html",
        }

    async def _fetch_html(self, url: str) -> dict[str, str]:
        raw = await self._fetch_raw(url)
        return {"url": raw["url"], "source": raw["source"], "html": raw["text"]}

    async def _fetch_raw(self, url: str) -> dict[str, Any]:
        safe_url = require_public_url(url)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            if self.bright_data_keys and self.bright_data_zone:
                try:
                    response, key_index = await self._request_brightdata(
                        client,
                        safe_url,
                        self.bright_data_zone,
                    )
                    source = "bright_data" if key_index == 0 else "bright_data_fallback"
                    response.raise_for_status()
                    return {
                        "url": safe_url,
                        "source": source,
                        "content": response.content,
                        "text": response.text,
                        "content_type": response.headers.get("content-type", ""),
                    }
                except Exception:
                    if os.environ.get("BRIGHTDATA_STRICT") == "1":
                        raise

            response = await self._fetch_native(client, safe_url)
            source = (
                "native_fetch_after_bright_data_error"
                if self.bright_data_keys and self.bright_data_zone
                else "native_fetch"
            )
            response.raise_for_status()
            return {
                "url": str(response.url),
                "source": source,
                "content": response.content,
                "text": response.text,
                "content_type": response.headers.get("content-type", ""),
            }

    async def _fetch_native(
        self,
        client: httpx.AsyncClient,
        safe_url: str,
    ) -> httpx.Response:
        return await client.get(
            safe_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                )
            },
        )

    async def _request_brightdata(
        self,
        client: httpx.AsyncClient,
        url: str,
        zone: str,
    ) -> tuple[httpx.Response, int]:
        last_response: httpx.Response | None = None
        for index, key in enumerate(self.bright_data_keys):
            response = await client.post(
                "https://api.brightdata.com/request",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "zone": zone,
                    "url": url,
                    "format": "raw",
                },
            )
            last_response = response
            # Keys may belong to different accounts/zones, so fail over to the
            # next key on ANY non-2xx (quota, auth, or zone-not-found 400s).
            if (
                not (200 <= response.status_code < 300)
                and index < len(self.bright_data_keys) - 1
            ):
                continue
            return response, index
        if last_response is None:
            raise RuntimeError("Bright Data is configured without an API key.")
        return last_response, len(self.bright_data_keys) - 1

    async def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        max_results = max(1, min(max_results, 10))
        # 1) Bright Data SERP (Google, structured JSON) — best discovery/coverage.
        if self.bright_data_keys and self.bright_data_serp_zone:
            try:
                serp = await self._search_brightdata_serp(query, max_results)
                if serp["results"]:
                    return serp
            except Exception:
                if os.environ.get("BRIGHTDATA_STRICT") == "1":
                    raise
        # 2) Fallback: DuckDuckGo HTML (fetched via unlocker/native).
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        fetched = await self._fetch_html(search_url)
        html = fetched["html"]
        links = extract_links(html, search_url, max_results)
        return {
            "query": query,
            "search_url": search_url,
            "source": fetched["source"],
            "results": [link.model_dump() for link in links],
            "text": extract_text(html, max_chars=5000),
        }

    async def _search_brightdata_serp(
        self,
        query: str,
        max_results: int,
    ) -> dict[str, Any]:
        num = min(max(max_results * 2, 10), 30)
        serp_url = (
            "https://www.google.com/search?"
            f"q={quote_plus(query)}&num={num}&brd_json=1"
        )
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response, _ = await self._request_brightdata(
                client,
                serp_url,
                self.bright_data_serp_zone,
            )
            response.raise_for_status()
            data = response.json()  # raises if the zone isn't SERP (-> caller falls back)

        organic = data.get("organic") or data.get("organic_results") or []
        results: list[AssistantSource] = []
        seen: set[str] = set()
        for item in organic:
            url = item.get("link") or item.get("url") or item.get("href")
            if not url:
                continue
            normalized = normalize_search_url(str(url))
            parsed = urlparse(normalized)
            if parsed.scheme not in {"http", "https"}:
                continue
            key = normalized.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            title = str(item.get("title") or normalized)[:160]
            snippet = item.get("description") or item.get("snippet") or item.get("desc")
            results.append(
                AssistantSource(
                    title=title,
                    url=normalized,
                    snippet=str(snippet)[:300] if snippet else None,
                    source="bright_data_serp",
                ),
            )
            if len(results) >= max_results:
                break
        return {
            "query": query,
            "search_url": serp_url,
            "source": "bright_data_serp",
            "results": [link.model_dump() for link in results],
            "text": "",
        }


def title_from_html(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:160]


def pdf_title_from_url(url: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1] or url
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"[-_]+", " ", name).strip()
    return (name or url)[:160]


def make_system_prompt(page_context: dict[str, Any]) -> str:
    context_json = json.dumps(page_context, ensure_ascii=False)[:6000]
    return (
        "You are the PolyFintech ESG Intelligence agent. You answer in concise, "
        "decision-useful prose for analysts using an ESG and financial dashboard.\n\n"
        "You know the current page context from this JSON. Treat Evidence Engine "
        "page context as the app's current model output, backed by local scoring "
        "logic, Bright Data news/report inputs, rater fields, and market-price "
        "signals. If context comes from a legacy/generated page, say so explicitly.\n"
        f"{context_json}\n\n"
        "Formatting rules: do not use emojis, decorative icons, or raw ASCII art. "
        "Use clean markdown headings, short paragraphs, bullets, and simple tables "
        "only when a table improves readability.\n\n"
        "ANSWER-FIRST: open with one bold sentence that directly answers the question, "
        "before any table, breakdown, or context. The reader should get the answer "
        "without reading further; supporting detail comes after.\n\n"
        "Prefer the current page_context company over older chat history when the "
        "user says this company, their, it, the selected company, or asks from a "
        "company page. "
        "Use get_company_esg whenever the user asks for THIS APP'S ESG score, a "
        "company's ESG estimate, why a company scored or is estimated as it is, or its "
        "underpriced-improver/quadrant status — it returns the same numbers the dashboard "
        "shows plus the estimate's feature drivers. Do not web-search for the app's own "
        "score/estimate; call get_company_esg. The estimate is EXPERIMENTAL — a model "
        "trained ONLY on real data (real evidence vs real news + price/sector signals); "
        "free signals weakly predict ESG, so present it as low-confidence (~60-80% "
        "hit-rate on a 10-company sample), cite its error, and explain 'why' via top_drivers. "
        "CRITICAL — when asked for a company's ESG score, the answer is the current "
        "EVIDENCE SCORE (that IS the ESG score). Lead with it: e.g. 'OCBC's ESG score is "
        "45/100.' Do NOT lead with, bold, or headline the forecast/2026 estimate as the "
        "score, and never conflate the two. The forecast is a separate forward-looking "
        "projection — mention it only afterwards, in its own clearly-labelled section, and "
        "only if relevant. One number is the answer (evidence score); the estimate is extra. "
        "Use research_company_esg_news when the user asks for current ESG news, "
        "recent sustainability developments, controversies, why a company score is "
        "high or low, or source-backed company ESG context. "
        "Use web_search or scrape_url when the user asks for current, latest, live, "
        "source-backed, regulatory, news, or webpage-specific information. Cite URLs "
        "you used in the answer. For public webpage scraping, never mention API keys "
        "or internal credentials. When the user asks how ESG scores are calculated, "
        "explained, justified, validated, or compared to outside sources, call "
        "research_esg_scoring first. Explain that the current app score is "
        "computed by the app's local ML/formula pipeline using report claims, "
        "SASB materiality weights, rater consensus, Bright Data news sentiment, "
        "and price-witness signals; do not describe it as an external ESG score "
        "API. Use the references to explain common ESG scoring inputs such as sector "
        "materiality, disclosures, controversies/news, governance, environmental "
        "and social indicators, provider-specific weighting, and uncertainty. If "
        "the user asks for a report, produce a complete "
        "markdown report with sections: Executive Summary, Key Findings, Evidence, "
        "Risks, and Next Steps."
    )


LangChainAgentFactory = Callable[[str], Any]


class OpenRouterAgent:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        web_tools: WebTools | None = None,
        langchain_agent_factory: LangChainAgentFactory | None = None,
        checkpointer: Any | None = None,
        max_recovery_attempts: int | None = None,
    ) -> None:
        self.api_key = api_key or env_first("OPENROUTER_API_KEY")
        self.model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.web_tools = web_tools or WebTools()
        self.tools = build_langchain_tools(self.web_tools)
        self.checkpointer = checkpointer or InMemorySaver()
        self.langchain_agent_factory = (
            langchain_agent_factory or self._create_langchain_agent
        )
        self.max_recovery_attempts = max(1, max_recovery_attempts or 3)

    async def run(self, request: AssistantRequest) -> AssistantResponse:
        if not self.api_key:
            # Graceful fallback: no API key -> the dashboard still runs on cached/
            # seeded data; only live chat is unavailable. Return a normal message
            # instead of a 500 so the UI degrades cleanly.
            return self._response(
                "The research assistant isn't configured on this deployment "
                "(no OPENROUTER_API_KEY). The dashboard is running on cached data; "
                "add an OpenRouter key to backend/.env to enable live chat.",
                [],
                [ToolResult(name="assistant", status="error",
                            summary="No OPENROUTER_API_KEY configured.", source_count=0)],
                [],
                [],
            )
        if not request.messages:
            raise HTTPException(status_code=400, detail="At least one message is required.")

        system_prompt = make_system_prompt(request.page_context)
        thread_id = request.session_id or "polyfintech-default"
        input_messages = [message_to_langchain_payload(request.messages[-1])]
        failures: list[str] = []

        for attempt in range(1, self.max_recovery_attempts + 1):
            langchain_agent = self.langchain_agent_factory(system_prompt)
            try:
                result = await langchain_agent.ainvoke(
                    {"messages": input_messages},
                    config={"configurable": {"thread_id": thread_id}},
                )
                result_messages = (
                    result.get("messages", []) if isinstance(result, dict) else []
                )
                final_content = extract_final_content(result_messages)
                (
                    tool_results,
                    sources,
                    workflow_steps,
                    reference_articles,
                ) = extract_tool_artifacts(result_messages)
                if failures:
                    recovery_summary = (
                        f"Recovered after {len(failures)} failed "
                        "agent attempt(s)."
                    )
                    tool_results.insert(
                        0,
                        ToolResult(
                            name="agent_recovery",
                            status="ok",
                            summary=recovery_summary,
                            source_count=0,
                        ),
                    )
                    workflow_steps.insert(
                        0,
                        WorkflowStep(
                            label="Recovered agent run",
                            status="ok",
                            detail=recovery_summary,
                            tool_name="agent_recovery",
                        ),
                    )
                return self._response(
                    final_content,
                    sources,
                    tool_results,
                    workflow_steps,
                    reference_articles,
                )
            except Exception as exc:
                failures.append(safe_error_summary(exc))

        return self._response(
            (
                "I couldn't complete that request after several recovery attempts. "
                "The dashboard is still available, but the assistant backend hit a "
                "provider or tool execution error. Try the same request again, or "
                "narrow it to one company or one source."
            ),
            [],
            [
                ToolResult(
                    name="agent_recovery",
                    status="error",
                    summary=(
                        f"Exhausted {self.max_recovery_attempts} recovery "
                        f"attempt(s). Last error: {failures[-1]}"
                    ),
                    source_count=0,
                )
            ],
            [
                WorkflowStep(
                    label="Agent recovery failed",
                    status="error",
                    detail=(
                        f"Exhausted {self.max_recovery_attempts} recovery "
                        f"attempt(s). Last error: {failures[-1]}"
                    ),
                    tool_name="agent_recovery",
                )
            ],
            [],
        )

    async def stream(self, request: AssistantRequest) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        token = WORKFLOW_EVENT_QUEUE.set(queue)
        task = asyncio.create_task(self.run(request))
        try:
            while not task.done() or not queue.empty():
                try:
                    step = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if step is None:
                    continue
                yield {
                    "type": "workflow",
                    "step": step.model_dump(by_alias=True),
                }

            response = await task
            yield {
                "type": "final",
                "response": response.model_dump(by_alias=True),
            }
        except Exception as exc:
            if not task.done():
                task.cancel()
            yield {
                "type": "error",
                "message": safe_error_summary(exc),
            }
        finally:
            WORKFLOW_EVENT_QUEUE.reset(token)

    def _create_langchain_agent(self, system_prompt: str) -> Any:
        model = ChatOpenRouter(
            model=self.model,
            api_key=self.api_key,
            temperature=0.25,
            max_tokens=1800,
            max_retries=2,
            app_url="http://localhost:5173",
            app_title="PolyFintech ESG Intelligence",
        )
        return create_agent(
            model=model,
            tools=self.tools,
            system_prompt=system_prompt,
            checkpointer=self.checkpointer,
            middleware=[
                ModelRetryMiddleware(max_retries=2),
                ToolRetryMiddleware(max_retries=1),
                ToolCallLimitMiddleware(run_limit=12, exit_behavior="error"),
            ],
            name="polyfintech-esg-agent",
        )

    def _response(
        self,
        content: str,
        sources: list[AssistantSource],
        tool_results: list[ToolResult],
        workflow_steps: list[WorkflowStep] | None = None,
        reference_articles: list[ReferenceArticle] | None = None,
    ) -> AssistantResponse:
        deduped_sources: list[AssistantSource] = []
        seen: set[str] = set()
        for source in sources:
            key = source.url.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            deduped_sources.append(source)

        deduped_reference_articles: list[ReferenceArticle] = []
        seen_articles: set[str] = set()
        for article in reference_articles or []:
            key = article.url.split("#", 1)[0]
            if key in seen_articles:
                continue
            seen_articles.add(key)
            deduped_reference_articles.append(article)

        report = None
        if is_report(content):
            title = first_heading(content) or "Generated ESG Report"
            report = ReportArtifact(
                title=title,
                markdown=content,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        return AssistantResponse(
            message=ChatMessage(role="assistant", content=content),
            sources=deduped_sources[:10],
            reference_articles=deduped_reference_articles[:8],
            tool_results=tool_results,
            workflow_steps=workflow_steps or [],
            report=report,
            model=self.model,
        )


def _engine_company_payload(company: str) -> dict | None:
    """Read the ESG engine's precomputed output — the SAME numbers the dashboard
    shows (evidence score, improver signal, and the ML next-year forecast with its
    feature drivers) — for a company resolved by id, ticker, or name."""
    from backend.engine import config

    out = config.OUT_DIR
    idx_path = out / "companies.json"
    if not idx_path.exists():
        return None
    try:
        companies = json.loads(idx_path.read_text("utf-8"))
    except Exception:
        return None
    q = (company or "").strip().lower()
    if not q:
        return None
    match = None
    for row in companies:
        cid = str(row.get("id", "")).lower()
        ticker = str(row.get("ticker", "")).lower()
        if q == cid or q == ticker or q == ticker.split(".")[0]:
            match = row
            break
    if match is None:
        for row in companies:  # fall back to a name contains-match
            if q in str(row.get("name", "")).lower():
                match = row
                break
    if match is None:
        return None

    dpath = out / "company" / f"{match['id']}.json"
    if not dpath.exists():
        return None
    try:
        d = json.loads(dpath.read_text("utf-8"))
    except Exception:
        return None

    ev = d.get("evidence", {}) or {}
    sig = d.get("signal", {}) or {}
    fc = d.get("forecast", {}) or {}
    raters = d.get("raters", {}) or {}
    drivers = sorted(
        fc.get("feature_contributions", []) or [],
        key=lambda c: -abs(c.get("contribution") or 0),
    )[:5]
    return {
        "company": {"id": match["id"], "name": match.get("name"),
                    "ticker": match.get("ticker"), "sector": match.get("sector")},
        "evidence_score": ev.get("total"),
        "pillars": ev.get("pillars"),
        "confidence": ev.get("confidence"),
        "signal": {
            "is_underpriced_improver": sig.get("is_underpriced_improver"),
            "proof_up": sig.get("proof_up"),
            "opinion_flat": sig.get("opinion_flat"),
            "price_flat": sig.get("price_flat"),
            "momentum": sig.get("momentum"),
            "evidence_gap": sig.get("evidence_gap"),
            "quadrant": sig.get("quadrant"),
        },
        "raters": {"consensus": raters.get("consensus"), "divergence": raters.get("divergence")},
        "forecast": {
            "predicted_score": fc.get("predicted_score"),
            "target_year": fc.get("target_year"),
            "horizon_years": fc.get("horizon_years"),
            "ci_low": fc.get("ci_low"),
            "ci_high": fc.get("ci_high"),
            "validation_mae": fc.get("val_error"),
            "hit_rate": fc.get("directional_accuracy"),
            "is_hypothesis": fc.get("hypothesis", True),
            "reliability_note": fc.get("drift_note"),
            "top_drivers": drivers,
        },
        "report_source": (d.get("claims", {}) or {}).get("source_url"),
    }


def build_langchain_tools(web_tools: WebTools) -> list[Any]:
    @tool
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the public web for current ESG, company, market, regulatory, or sustainability information."""
        try:
            result = await web_tools.search(query=query, max_results=max_results)
        except Exception as exc:
            summary = f"Search failed for: {query}. {safe_error_summary(exc)}"
            emit_workflow_step(
                label="Searched web",
                status="error",
                detail=summary,
                tool_name="web_search",
            )
            return json.dumps(
                {
                    "tool": "web_search",
                    "status": "error",
                    "summary": summary,
                    "sources": [],
                    "result": {"query": query},
                },
                ensure_ascii=False,
            )
        sources = [AssistantSource(**item) for item in result.get("results", [])]
        emit_workflow_step(
            label="Searched web",
            status="ok",
            detail=f"Searched web for: {query}",
            tool_name="web_search",
        )
        return json.dumps(
            {
                "tool": "web_search",
                "status": "ok",
                "summary": f"Searched web for: {query}",
                "sources": [source.model_dump(by_alias=True) for source in sources],
                "result": result,
            },
            ensure_ascii=False,
        )

    @tool
    async def scrape_url(url: str) -> str:
        """Retrieve and extract readable text from a public webpage URL."""
        try:
            result = await web_tools.fetch_url(url)
        except Exception as exc:
            summary = f"Scrape failed for: {url}. {safe_error_summary(exc)}"
            emit_workflow_step(
                label="Scraped page",
                status="error",
                detail=summary,
                tool_name="scrape_url",
            )
            return json.dumps(
                {
                    "tool": "scrape_url",
                    "status": "error",
                    "summary": summary,
                    "sources": [],
                    "result": {"url": url},
                },
                ensure_ascii=False,
            )
        source = AssistantSource(
            title=result["title"],
            url=result["url"],
            snippet=result["text"][:260],
            source=result["source"],
        )
        emit_workflow_step(
            label="Scraped page",
            status="ok",
            detail=f"Scraped {result['url']}",
            tool_name="scrape_url",
        )
        return json.dumps(
            {
                "tool": "scrape_url",
                "status": "ok",
                "summary": f"Scraped {result['url']}",
                "sources": [source.model_dump(by_alias=True)],
                "result": result,
            },
            ensure_ascii=False,
        )

    @tool
    async def research_company_esg_news(
        company: str,
        ticker: str | None = None,
        domain: str | None = None,
        max_results: int = 8,
    ) -> str:
        """Collect reliable company-specific ESG news, sustainability reports, controversies, and source references."""
        try:
            result = await collect_company_esg_news(
                web_tools=web_tools,
                company=company,
                ticker=ticker,
                domain=domain,
                max_results=max_results,
            )
        except Exception as exc:
            summary = (
                f"Company ESG/news collection failed for: {company}. "
                f"{safe_error_summary(exc)}"
            )
            emit_workflow_step(
                label="Collected company ESG news",
                status="error",
                detail=summary,
                tool_name="research_company_esg_news",
            )
            return json.dumps(
                {
                    "tool": "research_company_esg_news",
                    "status": "error",
                    "summary": summary,
                    "sources": [],
                    "referenceArticles": [],
                    "result": {"company": company},
                },
                ensure_ascii=False,
            )

        sources = result["sources"]
        articles = result["reference_articles"]
        status = "ok" if sources else "error"
        summary = (
            f"Collected {len(sources)} company ESG/news references for: {company}"
            if sources
            else f"No reliable company-specific ESG/news references found for: {company}"
        )
        emit_workflow_step(
            label="Collected company ESG news",
            status=status,
            detail=summary,
            tool_name="research_company_esg_news",
        )
        return json.dumps(
            {
                "tool": "research_company_esg_news",
                "status": status,
                "summary": summary,
                "sources": [source.model_dump(by_alias=True) for source in sources],
                "referenceArticles": [
                    article.model_dump(by_alias=True) for article in articles
                ],
                "result": {
                    "company": company,
                    "ticker": ticker,
                    "domain": domain,
                    "queries": result["queries"],
                    "errors": result["errors"],
                },
            },
            ensure_ascii=False,
        )

    @tool
    async def research_esg_scoring(
        topic: str = "ESG score methodology",
        company: str | None = None,
        max_results: int = 6,
    ) -> str:
        """Collect curated online references that explain ESG score methodology, drivers, controversies, and news context."""
        max_results = max(2, min(max_results, 8))
        queries = esg_research_queries(topic=topic, company=company)
        sources: list[AssistantSource] = []
        seen: set[str] = set()
        errors: list[str] = []
        for query in queries:
            if len(sources) >= max_results:
                break
            try:
                result = await web_tools.search(query=query, max_results=3)
            except Exception as exc:
                errors.append(f"{query}: {safe_error_summary(exc)}")
                emit_workflow_step(
                    label="Searched web",
                    status="error",
                    detail=f"Search failed for: {query}",
                    tool_name="web_search",
                )
                continue
            emit_workflow_step(
                label="Searched web",
                status="ok",
                detail=f"Searched web for: {query}",
                tool_name="web_search",
            )
            for item in result.get("results", []):
                source = AssistantSource(**item)
                key = source.url.split("#", 1)[0]
                if key in seen:
                    continue
                seen.add(key)
                sources.append(source)
                if len(sources) >= max_results:
                    break

        if len(sources) < max_results:
            if not sources:
                errors.append("Search returned no usable ESG reference links.")
            for source in fallback_esg_sources(max_results=max_results):
                key = source.url.split("#", 1)[0]
                if key in seen:
                    continue
                seen.add(key)
                sources.append(source)
                if len(sources) >= max_results:
                    break

        reference_articles = [
            reference_article_from_source(source, topic=topic, company=company)
            for source in sources
        ]
        summary_subject = company or topic
        status = "ok" if sources else "error"
        summary = (
            "Collected ESG methodology and article references for: "
            f"{summary_subject}"
            if sources
            else "Could not collect ESG references from the configured web search path."
        )
        emit_workflow_step(
            label="Collected ESG references",
            status=status,
            detail=summary,
            tool_name="research_esg_scoring",
        )
        return json.dumps(
            {
                "tool": "research_esg_scoring",
                "status": status,
                "summary": summary,
                "sources": [source.model_dump(by_alias=True) for source in sources],
                "referenceArticles": [
                    article.model_dump(by_alias=True) for article in reference_articles
                ],
                "result": {
                    "topic": topic,
                    "company": company,
                    "queries": queries,
                    "errors": errors,
                },
            },
            ensure_ascii=False,
        )

    @tool
    async def get_company_esg(company: str) -> str:
        """Return THIS APP'S own computed ESG evidence score, the underpriced-improver
        signal, and the ML next-year forecast (with the feature drivers behind it) for a
        company, resolved by id, ticker, or name. Use this — NOT a web search — whenever
        the user asks for the app's ESG score, why a company scored that way, its
        improver/quadrant status, or its predicted / forecast next-year ESG score. The
        forecast is a HYPOTHESIS from a local model; always state that and its validation
        error, and explain 'why' using top_drivers (the model's feature contributions)."""
        payload = await asyncio.to_thread(_engine_company_payload, company)
        if not payload:
            summary = (f"No engine ESG record found for '{company}'. It may be outside "
                       "the covered universe — try the exact company name or ticker.")
            emit_workflow_step(label="Read ESG engine", status="error",
                               detail=summary, tool_name="get_company_esg")
            return json.dumps({"tool": "get_company_esg", "status": "error",
                               "summary": summary, "sources": [],
                               "result": {"company": company}}, ensure_ascii=False)
        name = payload["company"]["name"]
        fc = payload["forecast"]
        summary = (f"{name}: ESG evidence {payload['evidence_score']}, live "
                   f"{fc.get('target_year') or ''} estimate {fc['predicted_score']} "
                   f"(real-time, MAE {fc['validation_mae']}).")
        sources = []
        if payload.get("report_source"):
            sources = [AssistantSource(title=f"{name} sustainability report",
                                       url=payload["report_source"],
                                       source="ESG Evidence Engine").model_dump(by_alias=True)]
        emit_workflow_step(label="Read ESG engine", status="ok",
                           detail=f"Read computed ESG + forecast for {name}",
                           tool_name="get_company_esg")
        return json.dumps({"tool": "get_company_esg", "status": "ok",
                           "summary": summary, "sources": sources,
                           "result": payload}, ensure_ascii=False)

    return [web_search, scrape_url, research_company_esg_news,
            research_esg_scoring, get_company_esg]


async def collect_company_esg_news(
    web_tools: WebTools,
    company: str,
    ticker: str | None = None,
    domain: str | None = None,
    max_results: int = 8,
) -> dict[str, Any]:
    company = company.strip()
    if not company:
        raise ValueError("Company name is required.")
    max_results = max(2, min(max_results, 10))
    queries = company_esg_news_queries(company=company, ticker=ticker, domain=domain)
    aliases = company_aliases(company=company, ticker=ticker)
    candidates: list[AssistantSource] = []
    seen: set[str] = set()
    errors: list[str] = []

    for query in queries:
        if len(candidates) >= max_results * 3:
            break
        try:
            result = await web_tools.search(query=query, max_results=6)
        except Exception as exc:
            errors.append(f"{query}: {safe_error_summary(exc)}")
            continue
        for item in result.get("results", []):
            source = AssistantSource(**item)
            key = source.url.split("#", 1)[0]
            if key in seen:
                continue
            if not is_company_specific_source(source, aliases=aliases, domain=domain):
                continue
            if not is_esg_news_source(source):
                continue
            seen.add(key)
            candidates.append(source)

    ranked_candidates = sorted(
        candidates,
        key=lambda source: source_reliability_score(source, domain=domain),
        reverse=True,
    )
    sources: list[AssistantSource] = []
    articles: list[ReferenceArticle] = []

    for candidate in ranked_candidates:
        if len(sources) >= max_results:
            break
        enriched = candidate
        try:
            fetched = await web_tools.fetch_url(candidate.url, max_chars=REPORT_FETCH_CHARS)
            text = str(fetched.get("text") or "")
            snippet = evidence_snippet(text, aliases=aliases) or candidate.snippet
            enriched = AssistantSource(
                title=str(fetched.get("title") or candidate.title),
                url=str(fetched.get("url") or candidate.url),
                snippet=snippet,
                source=str(fetched.get("source") or candidate.source),
            )
        except Exception as exc:
            errors.append(f"{candidate.url}: {safe_error_summary(exc)}")

        if not is_company_specific_source(enriched, aliases=aliases, domain=domain):
            continue
        kind = classify_company_esg_news_kind(enriched)
        sources.append(enriched)
        articles.append(
            ReferenceArticle(
                title=enriched.title,
                url=enriched.url,
                snippet=enriched.snippet,
                source=source_name_from_url(enriched.url) or enriched.source,
                kind=kind,
                reason=company_news_reason(kind, company=company),
            )
        )

    return {
        "queries": queries,
        "sources": sources,
        "reference_articles": articles,
        "errors": errors,
    }


ESG_NEWS_TERMS = {
    "esg",
    "sustainability",
    "sustainable",
    "climate",
    "carbon",
    "emissions",
    "renewable",
    "net zero",
    "net-zero",
    "governance",
    "board",
    "diversity",
    "labour",
    "labor",
    "human rights",
    "supply chain",
    "controversy",
    "controversies",
    "lawsuit",
    "fine",
    "probe",
    "investigation",
    "greenwashing",
    "deforestation",
    "pollution",
    "safety",
    "sustainability report",
    "annual report",
}

COMPANY_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "group",
    "holdings",
    "holding",
    "ltd",
    "limited",
    "plc",
    "sa",
    "ag",
    "nv",
    "se",
}


def company_esg_news_queries(
    company: str,
    ticker: str | None = None,
    domain: str | None = None,
) -> list[str]:
    quoted_company = f'"{company}"'
    queries = [
        f"{quoted_company} sustainability report 2024 filetype:pdf",
        f"{quoted_company} ESG report filetype:pdf",
        f"{quoted_company} ESG news sustainability controversy 2025 2026",
        f"{quoted_company} sustainability report ESG climate emissions governance",
        f"{quoted_company} ESG controversy climate governance news",
        f"{quoted_company} net zero emissions sustainability targets",
    ]
    if domain:
        # Prefer the company's own domain for the primary disclosure (the report itself).
        queries.insert(0, f"site:{domain} sustainability OR ESG report filetype:pdf")
        queries.insert(1, f"site:{domain} sustainability ESG report {quoted_company}")
    if ticker:
        queries.append(f'"{ticker}" "{company}" ESG sustainability report')
    return queries


def company_aliases(company: str, ticker: str | None = None) -> list[str]:
    normalized = normalize_text(company)
    aliases = [normalized]
    words = [
        word
        for word in re.split(r"\s+", normalized)
        if word and word not in COMPANY_SUFFIXES
    ]
    if len(words) >= 2:
        aliases.append(" ".join(words))
    if words:
        aliases.append(words[0])
    if ticker:
        ticker_clean = normalize_text(ticker.split(".", 1)[0])
        if len(ticker_clean) >= 2:
            aliases.append(ticker_clean)
    out: list[str] = []
    for alias in aliases:
        if alias and alias not in out:
            out.append(alias)
    return out


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def is_company_specific_source(
    source: AssistantSource,
    aliases: list[str],
    domain: str | None = None,
) -> bool:
    haystack = normalize_text(
        " ".join([source.title, source.url, source.snippet or ""]),
    )
    if domain:
        host = urlparse(source.url).hostname or ""
        clean_domain = domain.lower().removeprefix("www.")
        if host.lower().removeprefix("www.").endswith(clean_domain):
            return True
    return any(alias and alias in haystack for alias in aliases)


def is_esg_news_source(source: AssistantSource) -> bool:
    haystack = normalize_text(
        " ".join([source.title, source.url, source.snippet or ""]),
    )
    return any(normalize_text(term) in haystack for term in ESG_NEWS_TERMS)


def evidence_snippet(text: str, aliases: list[str], max_chars: int = 360) -> str | None:
    compact_text = re.sub(r"\s+", " ", text).strip()
    if not compact_text:
        return None
    lowered = compact_text.lower()
    terms = aliases + list(ESG_NEWS_TERMS)
    positions = [
        lowered.find(term)
        for term in terms
        if term and lowered.find(term) >= 0
    ]
    start = max(0, min(positions) - 80) if positions else 0
    snippet = compact_text[start : start + max_chars].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if start + max_chars < len(compact_text):
        snippet = f"{snippet}..."
    return snippet


def source_reliability_score(source: AssistantSource, domain: str | None = None) -> int:
    host = (urlparse(source.url).hostname or "").lower().removeprefix("www.")
    haystack = normalize_text(" ".join([source.title, source.url, source.snippet or ""]))
    score = 0
    if domain and host.endswith(domain.lower().removeprefix("www.")):
        score += 50
    # A PDF on the company's own domain is almost certainly the primary report.
    is_pdf = urlparse(source.url).path.lower().endswith(".pdf")
    if is_pdf:
        score += 25
    if any(term in haystack for term in ("sustainability report", "annual report", "esg report")):
        score += 20
    if any(
        trusted in host
        for trusted in (
            "reuters.com",
            "apnews.com",
            "bloomberg.com",
            "ft.com",
            "sec.gov",
            "msci.com",
            "spglobal.com",
            "sustainalytics.com",
        )
    ):
        score += 15
    if any(year in haystack for year in ("2026", "2025", "2024")):
        score += 8
    return score


def classify_company_esg_news_kind(source: AssistantSource) -> str:
    haystack = normalize_text(" ".join([source.title, source.url, source.snippet or ""]))
    if any(term in haystack for term in ("lawsuit", "fine", "probe", "investigation", "controversy", "greenwashing")):
        return "controversy"
    if any(term in haystack for term in ("sustainability report", "annual report", "esg report")):
        return "company_report"
    if any(term in haystack for term in ("rating", "score", "msci", "sustainalytics", "sp global")):
        return "rating_context"
    return "company_news"


def company_news_reason(kind: str, company: str) -> str:
    if kind == "controversy":
        return f"Flags controversy or risk context that may affect {company}'s ESG perception."
    if kind == "company_report":
        return f"Primary company disclosure for {company}'s sustainability targets and metrics."
    if kind == "rating_context":
        return f"Adds external rating or methodology context for interpreting {company}."
    return f"Company-specific ESG or sustainability news about {company}."


def esg_research_queries(topic: str, company: str | None = None) -> list[str]:
    base_topic = topic.strip() or "ESG score methodology"
    queries = [
        f"{base_topic} ESG scoring methodology",
        "how ESG ratings are calculated methodology sector materiality controversies",
        "MSCI ESG ratings methodology",
        "S&P Global ESG Scores methodology",
        "Sustainalytics ESG Risk Ratings methodology",
    ]
    if company:
        queries.insert(0, f"{company} ESG rating news controversy sustainability article")
        queries.insert(1, f"{company} sustainability report ESG score analysis")
    return queries


def fallback_esg_sources(max_results: int = 6) -> list[AssistantSource]:
    sources = [
        AssistantSource(
            title="MSCI ESG Ratings",
            url="https://www.msci.com/our-solutions/esg-investing/esg-ratings",
            snippet=(
                "Official MSCI overview of ESG ratings, intended to explain "
                "financially relevant ESG risks and opportunities."
            ),
            source="curated_reference",
        ),
        AssistantSource(
            title="S&P Global ESG Scores",
            url="https://www.spglobal.com/esg/solutions/data-intelligence-esg-scores",
            snippet=(
                "Official S&P Global page describing ESG score coverage, "
                "company disclosures, and sustainability intelligence."
            ),
            source="curated_reference",
        ),
        AssistantSource(
            title="Morningstar Sustainalytics ESG Risk Ratings",
            url="https://www.sustainalytics.com/esg-data",
            snippet=(
                "Official Sustainalytics ESG data page covering risk ratings, "
                "controversies, and issuer-level ESG research."
            ),
            source="curated_reference",
        ),
        AssistantSource(
            title="GRI Standards",
            url="https://www.globalreporting.org/standards/",
            snippet=(
                "Global Reporting Initiative standards for sustainability "
                "disclosures used as inputs by many ESG workflows."
            ),
            source="curated_reference",
        ),
        AssistantSource(
            title="IFRS Sustainability Standards Navigator",
            url="https://www.ifrs.org/issued-standards/ifrs-sustainability-standards-navigator/",
            snippet=(
                "ISSB/IFRS sustainability disclosure standards that help "
                "structure comparable sustainability reporting."
            ),
            source="curated_reference",
        ),
    ]
    return sources[: max(0, max_results)]


def reference_article_from_source(
    source: AssistantSource,
    topic: str,
    company: str | None = None,
) -> ReferenceArticle:
    kind = classify_reference_kind(source, topic=topic, company=company)
    return ReferenceArticle(
        title=source.title,
        url=source.url,
        snippet=source.snippet,
        source=source_name_from_url(source.url) or source.source,
        kind=kind,
        reason=reference_reason(kind, company=company),
    )


def classify_reference_kind(
    source: AssistantSource,
    topic: str,
    company: str | None = None,
) -> str:
    haystack = " ".join(
        item
        for item in (source.title, source.url, source.snippet or "", topic, company or "")
        if item
    ).lower()
    if any(term in haystack for term in ("sec", "regulation", "directive", "csrd", "issb")):
        return "regulatory"
    if any(term in haystack for term in ("news", "article", "controvers", "lawsuit")):
        return "news"
    if company and company.lower() in haystack:
        return "company"
    if any(term in haystack for term in ("methodolog", "rating", "score", "materiality")):
        return "methodology"
    return "article"


def reference_reason(kind: str, company: str | None = None) -> str:
    if kind == "methodology":
        return "Explains how ESG providers define, weight, or normalize score inputs."
    if kind == "regulatory":
        return "Adds disclosure or compliance context that can affect ESG interpretation."
    if kind == "company":
        subject = company or "the selected company"
        return f"Provides company-specific ESG context for {subject}."
    if kind == "news":
        return "Captures current controversy or news signals that may affect ESG perception."
    return "Provides supporting context for interpreting ESG scores."


def source_name_from_url(url: str) -> str | None:
    host = urlparse(url).hostname
    if not host:
        return None
    host = host.removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return host.replace("-", " ").title()


def message_to_langchain_payload(message: ChatMessage) -> dict[str, str]:
    role = "assistant" if message.role == "assistant" else "user"
    return {"role": role, "content": message.content}


def extract_final_content(messages: list[Any]) -> str:
    for message in reversed(messages):
        role = message_role(message)
        if role in {"assistant", "ai"}:
            return message_content(message)
    return ""


def message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "")
    return str(getattr(message, "role", None) or getattr(message, "type", ""))


def message_name(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("name") or "")
    return str(getattr(message, "name", "") or "")


def message_content(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    return str(content)


def extract_tool_artifacts(
    messages: list[Any],
) -> tuple[
    list[ToolResult],
    list[AssistantSource],
    list[WorkflowStep],
    list[ReferenceArticle],
]:
    tool_results: list[ToolResult] = []
    sources: list[AssistantSource] = []
    workflow_steps: list[WorkflowStep] = []
    reference_articles: list[ReferenceArticle] = []
    for message in messages:
        if message_role(message) not in {"tool"}:
            continue
        name = message_name(message) or "tool"
        raw_content = message_content(message)
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            parsed = {
                "tool": name,
                "status": "error",
                "summary": raw_content[:300] or "Tool returned an unreadable result.",
                "sources": [],
            }

        parsed_sources = [
            AssistantSource(**item) for item in parsed.get("sources", []) if item
        ]
        parsed_reference_articles = [
            ReferenceArticle(**item)
            for item in parsed.get("referenceArticles", parsed.get("reference_articles", []))
            if item
        ]
        sources.extend(parsed_sources)
        reference_articles.extend(parsed_reference_articles)
        tool_name = str(parsed.get("tool") or name)
        status = "ok" if parsed.get("status") == "ok" else "error"
        summary = str(parsed.get("summary") or raw_content[:300])
        tool_results.append(
            ToolResult(
                name=tool_name,
                status=status,
                summary=summary,
                source_count=len(parsed_sources),
            )
        )
        workflow_steps.append(
            WorkflowStep(
                label=workflow_label_for_tool(tool_name),
                status=status,
                detail=summary,
                tool_name=tool_name,
            )
        )
    return tool_results, sources, workflow_steps, reference_articles


def workflow_label_for_tool(tool_name: str) -> str:
    labels = {
        "web_search": "Searched web",
        "scrape_url": "Scraped page",
        "research_company_esg_news": "Collected company ESG news",
        "research_esg_scoring": "Collected ESG references",
        "agent_recovery": "Recovered agent run",
    }
    return labels.get(tool_name, tool_name.replace("_", " ").title())


def is_report(content: str) -> bool:
    lowered = content[:400].lower()
    heading = (first_heading(content) or "").lower()
    return "report" in heading or "# report" in lowered or (
        "executive summary" in lowered and "key findings" in lowered
    )


def first_heading(markdown: str) -> str | None:
    for line in markdown.splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            return clean.lstrip("#").strip()[:120]
    return None
