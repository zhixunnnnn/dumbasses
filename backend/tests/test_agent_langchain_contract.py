import asyncio
import json

import httpx
import backend.app.agent as agent_module
from backend.app.agent import (
    AssistantRequest,
    OpenRouterAgent,
    WebTools,
    build_langchain_tools,
    collect_company_esg_news,
    emit_workflow_step,
    extract_tool_artifacts,
    require_public_url,
)


class FakeLangChainAgent:
    def __init__(self, content: str) -> None:
        self.content = content
        self.payload = None
        self.config = None

    async def ainvoke(self, payload, config=None):
        self.payload = payload
        self.config = config
        return {
            "messages": [
                {"role": "assistant", "content": self.content},
            ],
        }


class FailsOnceLangChainAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, payload, config=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient provider timeout")
        return {
            "messages": [
                {"role": "assistant", "content": "Recovered answer."},
            ],
        }


class AlwaysFailsLangChainAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, payload, config=None):
        self.calls += 1
        raise RuntimeError("provider unavailable")


class EmitsWorkflowLangChainAgent:
    async def ainvoke(self, payload, config=None):
        emit_workflow_step(
            label="Searched web",
            status="ok",
            detail="Searched web for: DBS Group ESG score",
            tool_name="web_search",
        )
        return {
            "messages": [
                {"role": "assistant", "content": "Final source-backed answer."},
            ],
        }


class EmptySearchWebTools:
    async def search(self, query: str, max_results: int = 5):
        return {"query": query, "results": []}


class FakeCompanyNewsWebTools:
    async def search(self, query: str, max_results: int = 5):
        return {
            "query": query,
            "results": [
                {
                    "title": "Amazon ESG report outlines carbon and governance progress",
                    "url": "https://sustainability.aboutamazon.com/report",
                    "snippet": "Amazon sustainability report covers carbon, emissions, and governance.",
                    "source": "search",
                },
                {
                    "title": "Unrelated Tesla sustainability news",
                    "url": "https://example.com/tesla-esg",
                    "snippet": "Tesla carbon emissions update.",
                    "source": "search",
                },
            ],
        }

    async def fetch_url(self, url: str, max_chars: int = 0):
        return {
            "title": "Amazon Sustainability Report",
            "url": url,
            "source": "native_fetch",
            "text": (
                "Amazon sustainability report discusses ESG governance, "
                "carbon emissions, renewable energy, and supply chain progress."
            ),
        }


class FakeBrightDataResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.url = "https://api.brightdata.com/request"
        self.request = httpx.Request("POST", self.url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "Bright Data request failed.",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


def test_agent_invokes_langchain_factory_with_page_context_and_thread_id():
    created = {}

    def factory(system_prompt: str):
        agent = FakeLangChainAgent(
            "# ESG Report\n\n## Executive Summary\nLangChain generated this.",
        )
        created["system_prompt"] = system_prompt
        created["agent"] = agent
        return agent

    agent = OpenRouterAgent(
        api_key="test-key",
        model="test/model",
        langchain_agent_factory=factory,
    )
    request = AssistantRequest(
        messages=[{"role": "user", "content": "Generate a report."}],
        pageContext={"route": "company", "company": {"name": "Apple", "ticker": "AAPL"}},
        sessionId="thread-123",
    )

    response = asyncio.run(agent.run(request))

    assert "Apple" in created["system_prompt"]
    assert created["agent"].payload == {
        "messages": [{"role": "user", "content": "Generate a report."}],
    }
    assert created["agent"].config == {"configurable": {"thread_id": "thread-123"}}
    assert response.message.content.startswith("# ESG Report")
    assert response.report is not None
    assert response.report.title == "ESG Report"
    assert response.model == "test/model"


def test_agent_defaults_to_low_cost_tool_capable_openrouter_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    agent = OpenRouterAgent(
        api_key="test-key",
        langchain_agent_factory=lambda _system_prompt: FakeLangChainAgent("ok"),
    )

    assert agent.model == "deepseek/deepseek-v4-flash"


def test_agent_retries_langchain_failures_before_returning_response():
    fake_agent = FailsOnceLangChainAgent()

    agent = OpenRouterAgent(
        api_key="test-key",
        model="test/model",
        langchain_agent_factory=lambda _system_prompt: fake_agent,
        max_recovery_attempts=2,
    )
    request = AssistantRequest(
        messages=[{"role": "user", "content": "Summarize the page."}],
        pageContext={"route": "dashboard"},
        sessionId="recovery-thread",
    )

    response = asyncio.run(agent.run(request))

    assert fake_agent.calls == 2
    assert response.message.content == "Recovered answer."
    assert response.tool_results[0].name == "agent_recovery"
    assert response.tool_results[0].status == "ok"


def test_agent_returns_structured_fallback_after_recovery_attempts_exhausted():
    fake_agent = AlwaysFailsLangChainAgent()

    agent = OpenRouterAgent(
        api_key="test-key",
        model="test/model",
        langchain_agent_factory=lambda _system_prompt: fake_agent,
        max_recovery_attempts=2,
    )
    request = AssistantRequest(
        messages=[{"role": "user", "content": "Summarize the page."}],
        pageContext={"route": "dashboard"},
        sessionId="failing-thread",
    )

    response = asyncio.run(agent.run(request))

    assert fake_agent.calls == 2
    assert response.message.role == "assistant"
    assert "couldn't complete" in response.message.content
    assert response.tool_results[0].name == "agent_recovery"
    assert response.tool_results[0].status == "error"
    assert response.model == "test/model"


def test_agent_stream_emits_workflow_before_final_response():
    agent = OpenRouterAgent(
        api_key="test-key",
        model="test/model",
        langchain_agent_factory=lambda _system_prompt: EmitsWorkflowLangChainAgent(),
    )
    request = AssistantRequest(
        messages=[{"role": "user", "content": "Explain DBS ESG score."}],
        pageContext={"route": "company", "company": {"name": "DBS Group"}},
        sessionId="stream-thread",
    )

    async def collect_events():
        return [event async for event in agent.stream(request)]

    events = asyncio.run(collect_events())

    assert events[0]["type"] == "workflow"
    assert events[0]["step"]["detail"] == "Searched web for: DBS Group ESG score"
    assert events[-1]["type"] == "final"
    assert events[-1]["response"]["message"]["content"] == "Final source-backed answer."


def test_tool_messages_generate_workflow_steps_for_chat_ui():
    tool_payload = {
        "tool": "scrape_url",
        "status": "ok",
        "summary": "Scraped https://example.com",
        "sources": [
            {
                "title": "Example Domain",
                "url": "https://example.com",
                "snippet": "Example Domain",
                "source": "native_fetch",
            }
        ],
    }

    tool_results, sources, workflow_steps, reference_articles = extract_tool_artifacts(
        [
            {
                "role": "tool",
                "name": "scrape_url",
                "content": json.dumps(tool_payload),
            }
        ]
    )

    assert tool_results[0].name == "scrape_url"
    assert sources[0].url == "https://example.com"
    assert reference_articles == []
    assert workflow_steps[0].tool_name == "scrape_url"
    assert workflow_steps[0].status == "ok"
    assert workflow_steps[0].label == "Scraped page"
    assert workflow_steps[0].detail == "Scraped https://example.com"


def test_esg_research_tool_artifacts_include_reference_articles_for_chat_ui():
    tool_payload = {
        "tool": "research_esg_scoring",
        "status": "ok",
        "summary": "Collected ESG methodology and article references.",
        "sources": [
            {
                "title": "ESG Ratings Methodology",
                "url": "https://example.com/esg-methodology",
                "snippet": "ESG ratings combine sector materiality and company disclosures.",
                "source": "native_fetch",
            }
        ],
        "referenceArticles": [
            {
                "title": "How ESG ratings are calculated",
                "url": "https://example.com/esg-methodology",
                "snippet": "ESG ratings combine sector materiality and company disclosures.",
                "source": "Example Research",
                "kind": "methodology",
                "reason": "Explains common ESG score inputs and weighting.",
            }
        ],
    }

    tool_results, sources, workflow_steps, reference_articles = extract_tool_artifacts(
        [
            {
                "role": "tool",
                "name": "research_esg_scoring",
                "content": json.dumps(tool_payload),
            }
        ]
    )

    assert tool_results[0].name == "research_esg_scoring"
    assert sources[0].url == "https://example.com/esg-methodology"
    assert workflow_steps[0].label == "Collected ESG references"
    assert reference_articles[0].kind == "methodology"
    assert reference_articles[0].reason == "Explains common ESG score inputs and weighting."


def test_langchain_toolkit_includes_dedicated_esg_research_tool():
    tool_names = {tool.name for tool in build_langchain_tools(object())}

    assert "research_esg_scoring" in tool_names
    assert "research_company_esg_news" in tool_names


def test_esg_research_tool_returns_curated_fallback_references_when_search_is_empty():
    tools = build_langchain_tools(EmptySearchWebTools())
    research_tool = next(tool for tool in tools if tool.name == "research_esg_scoring")

    payload = asyncio.run(
        research_tool.ainvoke({"topic": "ESG score methodology", "max_results": 4})
    )
    parsed = json.loads(payload)

    assert parsed["status"] == "ok"
    assert len(parsed["referenceArticles"]) >= 3
    assert parsed["referenceArticles"][0]["kind"] == "methodology"


def test_company_esg_news_collector_filters_and_enriches_company_sources():
    result = asyncio.run(
        collect_company_esg_news(
            web_tools=FakeCompanyNewsWebTools(),
            company="Amazon",
            ticker="AMZN",
            domain="amazon.com",
            max_results=4,
        )
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0].url == "https://sustainability.aboutamazon.com/report"
    assert "carbon emissions" in result["sources"][0].snippet
    assert result["reference_articles"][0].kind == "company_report"
    assert "Amazon" in result["reference_articles"][0].reason


def test_webtools_uses_default_brightdata_zone_when_key_exists(monkeypatch):
    zones: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, headers, json):
            zones.append(json["zone"])
            return FakeBrightDataResponse(
                200,
                "<html><title>Default Zone OK</title><body>Loaded.</body></html>",
            )

    for name in (
        "BRIGHTDATA_ZONE",
        "BRIGHT_DATA_ZONE",
        "BRIGHTDATA_WEB_UNLOCKER_ZONE",
        "BRIGHT_DATA_WEB_UNLOCKER_ZONE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "primary-key")
    monkeypatch.delenv("BRIGHTDATA_API_KEY_FALLBACK", raising=False)
    monkeypatch.setattr(agent_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(WebTools().fetch_url("https://example.com"))

    assert zones == ["web_unlocker1"]
    assert result["source"] == "bright_data"
    assert result["url"] == "https://example.com"


def test_webtools_falls_back_to_second_brightdata_key_on_quota_failure(monkeypatch):
    calls: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url, headers, json):
            token = headers["Authorization"].removeprefix("Bearer ")
            calls.append(token)
            if token == "primary-key":
                return FakeBrightDataResponse(402, "quota exhausted")
            return FakeBrightDataResponse(
                200,
                "<html><title>Fallback OK</title><body>Loaded by fallback.</body></html>",
            )

    monkeypatch.setenv("BRIGHTDATA_API_KEY", "primary-key")
    monkeypatch.setenv("BRIGHTDATA_API_KEY_FALLBACK", "fallback-key")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "web-unlocker")
    monkeypatch.setattr(agent_module.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(WebTools().fetch_url("https://example.com"))

    assert calls == ["primary-key", "fallback-key"]
    assert result["source"] == "bright_data_fallback"
    assert result["title"] == "Fallback OK"


def test_require_public_url_rejects_private_targets():
    for url in ("http://localhost:8000", "http://127.0.0.1:5173"):
        try:
            require_public_url(url)
        except ValueError as exc:
            assert "Local/private URLs" in str(exc)
        else:
            raise AssertionError(f"{url} should have been rejected")
