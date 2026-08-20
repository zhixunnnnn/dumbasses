"""Agent-response feedback store — flags raised in the UI, reviewed in Governance.

One row per flag. The row keeps the prompt, the response, and the evidence the
agent surfaced, so a reviewer can judge the answer without replaying the session
and so the row can be exported as an RLHF preference pair (rejected = the flagged
response, chosen = the reviewer's correction).

Lives in the same SQLite file as chat history so a deployment needs one volume.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .chat_history import DEFAULT_CHAT_HISTORY_DB

FeedbackStatus = Literal["open", "reviewing", "resolved", "dismissed"]
FeedbackRating = Literal["flag", "down", "up"]

REASONS = {
    "inaccurate": "Factually wrong",
    "unsupported": "Not supported by the cited sources",
    "fabricated": "Fabricated source or number",
    "incomplete": "Missed part of the question",
    "off_topic": "Did not answer the question",
    "tone": "Tone or formatting problem",
    "unsafe": "Unsafe or inappropriate",
    "other": "Other",
}
STATUSES: tuple[FeedbackStatus, ...] = ("open", "reviewing", "resolved", "dismissed")


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FeedbackCreate(ApiModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    message_id: str | None = Field(default=None, alias="messageId")
    rating: FeedbackRating = "flag"
    reason: str = "other"
    comment: str = ""
    response_text: str = Field(default="", alias="responseText")
    prompt_text: str = Field(default="", alias="promptText")
    model: str | None = None
    surface: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    page_context: dict[str, Any] = Field(default_factory=dict, alias="pageContext")


class FeedbackReview(ApiModel):
    status: FeedbackStatus | None = None
    reviewer_note: str | None = Field(default=None, alias="reviewerNote")
    corrected_response: str | None = Field(default=None, alias="correctedResponse")
    reviewer: str | None = None


class FeedbackRecord(ApiModel):
    id: str
    session_id: str | None = Field(default=None, alias="sessionId")
    message_id: str | None = Field(default=None, alias="messageId")
    created_at: str = Field(alias="createdAt")
    rating: str
    reason: str
    reason_label: str = Field(alias="reasonLabel")
    comment: str
    response_text: str = Field(alias="responseText")
    prompt_text: str = Field(alias="promptText")
    model: str | None = None
    surface: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    page_context: dict[str, Any] = Field(default_factory=dict, alias="pageContext")
    status: str
    reviewer: str | None = None
    reviewer_note: str = Field(default="", alias="reviewerNote")
    corrected_response: str = Field(default="", alias="correctedResponse")
    reviewed_at: str | None = Field(default=None, alias="reviewedAt")


class FeedbackStore:
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
                CREATE TABLE IF NOT EXISTS message_feedback (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    message_id TEXT,
                    created_at TEXT NOT NULL,
                    rating TEXT NOT NULL DEFAULT 'flag',
                    reason TEXT NOT NULL DEFAULT 'other',
                    comment TEXT NOT NULL DEFAULT '',
                    response_text TEXT NOT NULL DEFAULT '',
                    prompt_text TEXT NOT NULL DEFAULT '',
                    model TEXT,
                    surface TEXT,
                    artifacts_json TEXT NOT NULL DEFAULT '{}',
                    page_context_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'open',
                    reviewer TEXT,
                    reviewer_note TEXT NOT NULL DEFAULT '',
                    corrected_response TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_created
                    ON message_feedback(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_status
                    ON message_feedback(status, created_at DESC);
                """
            )

    def create(self, payload: FeedbackCreate) -> FeedbackRecord:
        reason = payload.reason if payload.reason in REASONS else "other"
        record_id = f"fb-{uuid.uuid4().hex}"
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO message_feedback (
                    id, session_id, message_id, created_at, rating, reason, comment,
                    response_text, prompt_text, model, surface,
                    artifacts_json, page_context_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    record_id,
                    payload.session_id,
                    payload.message_id,
                    created_at,
                    payload.rating,
                    reason,
                    payload.comment.strip()[:4000],
                    payload.response_text[:20000],
                    payload.prompt_text[:8000],
                    payload.model,
                    payload.surface,
                    _dump(payload.artifacts),
                    _dump(payload.page_context),
                ),
            )
        return self.get(record_id)

    def get(self, feedback_id: str) -> FeedbackRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM message_feedback WHERE id = ?", (feedback_id,)
            ).fetchone()
        if not row:
            raise KeyError(feedback_id)
        return _record(row)

    def list(self, status: str | None = None, limit: int = 200) -> list[FeedbackRecord]:
        query = "SELECT * FROM message_feedback"
        params: list[Any] = []
        if status and status != "all":
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_record(row) for row in rows]

    def review(self, feedback_id: str, payload: FeedbackReview) -> FeedbackRecord:
        current = self.get(feedback_id)
        status = payload.status or current.status
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE message_feedback
                SET status = ?, reviewer = ?, reviewer_note = ?,
                    corrected_response = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    payload.reviewer if payload.reviewer is not None else current.reviewer,
                    (
                        payload.reviewer_note
                        if payload.reviewer_note is not None
                        else current.reviewer_note
                    )[:8000],
                    (
                        payload.corrected_response
                        if payload.corrected_response is not None
                        else current.corrected_response
                    )[:20000],
                    _now(),
                    feedback_id,
                ),
            )
        return self.get(feedback_id)

    def delete(self, feedback_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM message_feedback WHERE id = ?", (feedback_id,)
            )
            return cursor.rowcount > 0

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            by_status = connection.execute(
                "SELECT status, COUNT(*) AS n FROM message_feedback GROUP BY status"
            ).fetchall()
            by_reason = connection.execute(
                "SELECT reason, COUNT(*) AS n FROM message_feedback GROUP BY reason"
            ).fetchall()
            trainable = connection.execute(
                """
                SELECT COUNT(*) AS n FROM message_feedback
                WHERE status = 'resolved' AND TRIM(corrected_response) <> ''
                """
            ).fetchone()
            latest = connection.execute(
                "SELECT MAX(created_at) AS ts FROM message_feedback"
            ).fetchone()
        return {
            "total": sum(int(row["n"]) for row in by_status),
            "byStatus": {row["status"]: int(row["n"]) for row in by_status},
            "byReason": {row["reason"]: int(row["n"]) for row in by_reason},
            "reasonLabels": REASONS,
            "trainablePairs": int(trainable["n"]) if trainable else 0,
            "latestAt": latest["ts"] if latest else None,
        }

    def export_jsonl(self, only_corrected: bool = True) -> str:
        """RLHF preference pairs: rejected = the flagged answer, chosen = the human
        correction. Rows without a correction carry no preference signal, so they
        are excluded unless explicitly requested."""
        rows = self.list(status=None, limit=1000)
        lines: list[str] = []
        for row in rows:
            if only_corrected and not row.corrected_response.strip():
                continue
            lines.append(
                json.dumps(
                    {
                        "id": row.id,
                        "prompt": row.prompt_text,
                        "rejected": row.response_text,
                        "chosen": row.corrected_response or None,
                        "reason": row.reason,
                        "reason_label": row.reason_label,
                        "annotator_comment": row.comment,
                        "reviewer_note": row.reviewer_note,
                        "status": row.status,
                        "model": row.model,
                        "created_at": row.created_at,
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines) + ("\n" if lines else "")


def _record(row: sqlite3.Row) -> FeedbackRecord:
    reason = row["reason"]
    return FeedbackRecord(
        id=row["id"],
        session_id=row["session_id"],
        message_id=row["message_id"],
        created_at=row["created_at"],
        rating=row["rating"],
        reason=reason,
        reason_label=REASONS.get(reason, REASONS["other"]),
        comment=row["comment"],
        response_text=row["response_text"],
        prompt_text=row["prompt_text"],
        model=row["model"],
        surface=row["surface"],
        artifacts=_load(row["artifacts_json"], {}),
        page_context=_load(row["page_context_json"], {}),
        status=row["status"],
        reviewer=row["reviewer"],
        reviewer_note=row["reviewer_note"],
        corrected_response=row["corrected_response"],
        reviewed_at=row["reviewed_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
