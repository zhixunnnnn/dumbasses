from pathlib import Path

from backend.app.agent import (
    AssistantResponse,
    AssistantSource,
    ChatMessage,
    ReferenceArticle,
    ToolResult,
    WorkflowStep,
)
from backend.app.chat_history import ChatHistoryStore


TEST_DB_DIR = Path(__file__).parent / ".tmp"


def make_store(name: str) -> ChatHistoryStore:
    TEST_DB_DIR.mkdir(exist_ok=True)
    path = TEST_DB_DIR / name
    if path.exists():
        path.unlink()
    return ChatHistoryStore(path)


def test_chat_history_persists_sessions_messages_and_artifacts():
    store = make_store("persist.sqlite3")
    session = store.create_session(title="New ESG chat", session_id="session-a")

    user_message = store.append_user_message(
        session.id,
        "Explain DBS Group ESG score from this page",
        {"route": "company", "company": {"name": "DBS Group"}},
        message_id="user-1",
    )
    response = AssistantResponse(
        message=ChatMessage(role="assistant", content="DBS explanation."),
        sources=[
            AssistantSource(
                title="DBS Sustainability",
                url="https://www.dbs.com/sustainability",
                snippet="Sustainability report",
                source="native_fetch",
            )
        ],
        referenceArticles=[
            ReferenceArticle(
                title="MSCI ESG Ratings",
                url="https://www.msci.com/",
                snippet="Methodology",
                source="MSCI",
                kind="methodology",
                reason="Explains ESG ratings.",
            )
        ],
        toolResults=[
            ToolResult(
                name="web_search",
                status="ok",
                summary="Searched DBS ESG",
                sourceCount=1,
            )
        ],
        workflowSteps=[
            WorkflowStep(
                label="Searched web",
                status="ok",
                detail="Searched DBS ESG",
                toolName="web_search",
            )
        ],
        model="test/model",
    )

    assistant_message = store.append_assistant_response(
        session.id,
        response,
        {"route": "company", "company": {"name": "DBS Group"}},
    )
    detail = store.get_session(session.id)

    assert user_message.id == "user-1"
    assert assistant_message.sources[0]["title"] == "DBS Sustainability"
    assert detail.session.title == "Explain DBS Group ESG score from this page"
    assert detail.session.message_count == 2
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].reference_articles[0]["source"] == "MSCI"
    assert detail.messages[1].tool_results[0]["name"] == "web_search"
    assert detail.messages[1].page_context["company"]["name"] == "DBS Group"


def test_chat_history_lists_recent_sessions_first():
    store = make_store("order.sqlite3")
    older = store.create_session(title="Older", session_id="older")
    newer = store.create_session(title="Newer", session_id="newer")

    store.append_user_message(older.id, "old message", {"route": "dashboard"})
    store.append_user_message(newer.id, "new message", {"route": "dashboard"})

    sessions = store.list_sessions()

    assert sessions[0].id == newer.id
    assert {session.id for session in sessions} == {"older", "newer"}


def test_chat_history_ensures_frontend_supplied_session_id():
    store = make_store("ensure.sqlite3")

    session = store.ensure_session("session-from-browser")

    assert session.id == "session-from-browser"
    assert session.title == "New ESG chat"
