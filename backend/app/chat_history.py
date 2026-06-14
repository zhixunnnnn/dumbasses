from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent import AssistantResponse, ChatMessage


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHAT_HISTORY_DB = ROOT / "backend" / "data" / "chat_history.sqlite3"


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ChatSessionSummary(ApiModel):
    id: str
    title: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    message_count: int = Field(default=0, alias="messageCount")


class StoredChatMessage(ApiModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str = Field(alias="createdAt")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reference_articles: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="referenceArticles",
    )
    tool_results: list[dict[str, Any]] = Field(default_factory=list, alias="toolResults")
    workflow_steps: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="workflowSteps",
    )
    report: dict[str, Any] | None = None
    model: str | None = None
    page_context: dict[str, Any] = Field(default_factory=dict, alias="pageContext")


class ChatSessionDetail(ApiModel):
    session: ChatSessionSummary
    messages: list[StoredChatMessage]


class CreateChatSessionRequest(ApiModel):
    title: str | None = None


class ChatHistoryStore:
    def __init__(self, path: Path | str = DEFAULT_CHAT_HISTORY_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    page_context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    reference_articles_json TEXT NOT NULL DEFAULT '[]',
                    tool_results_json TEXT NOT NULL DEFAULT '[]',
                    workflow_steps_json TEXT NOT NULL DEFAULT '[]',
                    report_json TEXT,
                    model TEXT,
                    page_context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                    ON chat_messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
                    ON chat_sessions(updated_at DESC);
                """
            )

    def create_session(self, title: str | None = None, session_id: str | None = None) -> ChatSessionSummary:
        now = now_iso()
        resolved_id = session_id or f"session-{uuid.uuid4().hex}"
        resolved_title = clean_title(title) or "New ESG chat"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_sessions
                    (id, title, created_at, updated_at, page_context_json)
                VALUES (?, ?, ?, ?, '{}')
                """,
                (resolved_id, resolved_title, now, now),
            )
        return self.get_session_summary(resolved_id)

    def ensure_session(self, session_id: str | None, title: str | None = None) -> ChatSessionSummary:
        if not session_id:
            return self.create_session(title=title)
        existing = self.get_session_summary_or_none(session_id)
        if existing:
            return existing
        return self.create_session(title=title, session_id=session_id)

    def list_sessions(self) -> list[ChatSessionSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                    COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [session_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> ChatSessionDetail:
        session = self.get_session_summary_or_none(session_id)
        if not session:
            raise KeyError(session_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return ChatSessionDetail(
            session=session,
            messages=[message_from_row(row) for row in rows],
        )

    def get_session_summary(self, session_id: str) -> ChatSessionSummary:
        summary = self.get_session_summary_or_none(session_id)
        if not summary:
            raise KeyError(session_id)
        return summary

    def get_session_summary_or_none(self, session_id: str) -> ChatSessionSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                    COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (session_id,),
            ).fetchone()
        return session_from_row(row) if row else None

    def append_user_message(
        self,
        session_id: str,
        content: str,
        page_context: dict[str, Any],
        message_id: str | None = None,
    ) -> StoredChatMessage:
        session = self.ensure_session(session_id)
        message = self._insert_message(
            session_id=session.id,
            role="user",
            content=content,
            page_context=page_context,
            message_id=message_id,
        )
        if session.title == "New ESG chat":
            self.rename_session(session.id, title_from_content(content))
        self.touch_session(session.id, page_context=page_context)
        return message

    def append_assistant_response(
        self,
        session_id: str,
        response: AssistantResponse,
        page_context: dict[str, Any],
    ) -> StoredChatMessage:
        message = self._insert_message(
            session_id=session_id,
            role=response.message.role,
            content=response.message.content,
            page_context=page_context,
            sources=[item.model_dump(by_alias=True) for item in response.sources],
            reference_articles=[
                item.model_dump(by_alias=True) for item in response.reference_articles
            ],
            tool_results=[item.model_dump(by_alias=True) for item in response.tool_results],
            workflow_steps=[
                item.model_dump(by_alias=True) for item in response.workflow_steps
            ],
            report=response.report.model_dump(by_alias=True) if response.report else None,
            model=response.model,
        )
        self.touch_session(session_id, page_context=page_context)
        return message

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def rename_session(self, session_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (clean_title(title) or "New ESG chat", now_iso(), session_id),
            )

    def touch_session(self, session_id: str, page_context: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, page_context_json = ?
                WHERE id = ?
                """,
                (now_iso(), json_dump(page_context), session_id),
            )

    def _insert_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
        page_context: dict[str, Any],
        message_id: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        reference_articles: list[dict[str, Any]] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        workflow_steps: list[dict[str, Any]] | None = None,
        report: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> StoredChatMessage:
        created_at = now_iso()
        resolved_id = message_id or f"msg-{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    id, session_id, role, content, created_at,
                    sources_json, reference_articles_json, tool_results_json,
                    workflow_steps_json, report_json, model, page_context_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    session_id,
                    role,
                    content,
                    created_at,
                    json_dump(sources or []),
                    json_dump(reference_articles or []),
                    json_dump(tool_results or []),
                    json_dump(workflow_steps or []),
                    json_dump(report) if report else None,
                    model,
                    json_dump(page_context),
                ),
            )
        return StoredChatMessage(
            id=resolved_id,
            role=role,
            content=content,
            created_at=created_at,
            sources=sources or [],
            reference_articles=reference_articles or [],
            tool_results=tool_results or [],
            workflow_steps=workflow_steps or [],
            report=report,
            model=model,
            page_context=page_context,
        )


def session_from_row(row: sqlite3.Row) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=int(row["message_count"]),
    )


def message_from_row(row: sqlite3.Row) -> StoredChatMessage:
    return StoredChatMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        sources=json_load(row["sources_json"], []),
        reference_articles=json_load(row["reference_articles_json"], []),
        tool_results=json_load(row["tool_results_json"], []),
        workflow_steps=json_load(row["workflow_steps_json"], []),
        report=json_load(row["report_json"], None) if row["report_json"] else None,
        model=row["model"],
        page_context=json_load(row["page_context_json"], {}),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re_space(value)
    return cleaned[:72] if cleaned else None


def title_from_content(content: str) -> str:
    cleaned = re_space(content)
    if not cleaned:
        return "New ESG chat"
    return cleaned[:56]


def re_space(value: str) -> str:
    return " ".join(value.strip().split())


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_load(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def chat_message_from_stored(message: StoredChatMessage) -> ChatMessage:
    return ChatMessage(role=message.role, content=message.content)
