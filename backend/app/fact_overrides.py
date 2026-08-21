"""Reviewer-authored fact overrides — the deterministic half of the feedback loop.

When a flagged answer is wrong about a *specific* number (this company, this
field), a fuzzy correction retrieved by similarity is the wrong tool: it may or
may not match next time, and the model may or may not honour it. Instead the
reviewer pins the correct value here, keyed by (company_id, field). Every agent
read of that company's ESG payload is patched before the model sees it, so the
model cannot answer with the stale number — there is nothing to ignore.

Lives in the same SQLite file as chat history and feedback, NOT in esg.db: the
engine rebuilds esg.db on every pipeline run, and a human correction must
outlive that.
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

FieldKind = Literal["number", "text"]

# Only these paths into `_engine_company_payload` may be overridden. Anything
# else is rejected: an open-ended path would let a reviewer graft arbitrary keys
# onto the payload the model reads.
OVERRIDABLE_FIELDS: dict[str, dict[str, Any]] = {
    "evidence_score": {
        "label": "Evidence score",
        "kind": "number",
        "min": 0.0,
        "max": 100.0,
        "hint": "Composite evidence score, 0-100",
    },
    "pillars.E": {"label": "Pillar E", "kind": "number", "min": 0.0, "max": 100.0},
    "pillars.S": {"label": "Pillar S", "kind": "number", "min": 0.0, "max": 100.0},
    "pillars.G": {"label": "Pillar G", "kind": "number", "min": 0.0, "max": 100.0},
    "confidence": {
        "label": "Confidence",
        "kind": "number",
        "min": 0.0,
        "max": 1.0,
        "hint": "0-1, not a percentage",
    },
    "raters.consensus": {
        "label": "Rater consensus",
        "kind": "number",
        "min": 0.0,
        "max": 100.0,
    },
    "raters.divergence": {
        "label": "Rater divergence",
        "kind": "number",
        "min": 0.0,
        "max": 100.0,
    },
    "forecast.predicted_score": {
        "label": "Forecast: predicted score",
        "kind": "number",
        "min": 0.0,
        "max": 100.0,
    },
    "report_source": {
        "label": "Report source URL",
        "kind": "text",
        "hint": "The sustainability report the figures come from",
    },
}


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class OverrideCreate(ApiModel):
    company_id: str = Field(alias="companyId")
    field: str
    value: Any
    note: str = ""
    source_url: str = Field(default="", alias="sourceUrl")
    feedback_id: str | None = Field(default=None, alias="feedbackId")
    reviewer: str | None = None
    expires_at: str | None = Field(default=None, alias="expiresAt")


class OverrideRecord(ApiModel):
    id: str
    company_id: str = Field(alias="companyId")
    field: str
    field_label: str = Field(alias="fieldLabel")
    value: Any
    note: str
    source_url: str = Field(alias="sourceUrl")
    feedback_id: str | None = Field(default=None, alias="feedbackId")
    reviewer: str | None = None
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    expires_at: str | None = Field(default=None, alias="expiresAt")
    is_expired: bool = Field(alias="isExpired")


def validate_field_value(field: str, value: Any) -> Any:
    """Reject unknown fields and coerce/bound the value. Raises ValueError."""
    spec = OVERRIDABLE_FIELDS.get(field)
    if spec is None:
        raise ValueError(f"'{field}' is not an overridable field")
    if spec["kind"] == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{spec['label']} must be a number") from None
        low, high = spec.get("min"), spec.get("max")
        if low is not None and number < low:
            raise ValueError(f"{spec['label']} must be at least {low}")
        if high is not None and number > high:
            raise ValueError(f"{spec['label']} must be at most {high}")
        return number
    text = str(value).strip()
    if not text:
        raise ValueError(f"{spec['label']} cannot be empty")
    return text


def normalize_expiry(value: str | None) -> str | None:
    """A bare `YYYY-MM-DD` means end of that day, so an override stays live for
    the whole of its final day rather than expiring at midnight."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10:
        return f"{text}T23:59:59+00:00"
    return text


class FactOverrideStore:
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
                CREATE TABLE IF NOT EXISTS fact_overrides (
                    id          TEXT PRIMARY KEY,
                    company_id  TEXT NOT NULL,
                    field       TEXT NOT NULL,
                    value_json  TEXT NOT NULL,
                    note        TEXT NOT NULL DEFAULT '',
                    source_url  TEXT NOT NULL DEFAULT '',
                    feedback_id TEXT,
                    reviewer    TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    expires_at  TEXT
                );

                -- One live value per field: a second override on the same field
                -- would make the applied value depend on row order.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_override_company_field
                    ON fact_overrides(company_id, field);
                """
            )

    def upsert(self, payload: OverrideCreate) -> OverrideRecord:
        company_id = payload.company_id.strip()
        if not company_id:
            raise ValueError("companyId is required")
        value = validate_field_value(payload.field, payload.value)
        expires_at = normalize_expiry(payload.expires_at)
        now = _now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM fact_overrides WHERE company_id = ? AND field = ?",
                (company_id, payload.field),
            ).fetchone()
            record_id = existing["id"] if existing else f"ov-{uuid.uuid4().hex}"
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO fact_overrides (
                    id, company_id, field, value_json, note, source_url,
                    feedback_id, reviewer, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, field) DO UPDATE SET
                    value_json  = excluded.value_json,
                    note        = excluded.note,
                    source_url  = excluded.source_url,
                    feedback_id = excluded.feedback_id,
                    reviewer    = excluded.reviewer,
                    updated_at  = excluded.updated_at,
                    expires_at  = excluded.expires_at
                """,
                (
                    record_id,
                    company_id,
                    payload.field,
                    json.dumps(value),
                    payload.note.strip()[:2000],
                    payload.source_url.strip()[:1000],
                    payload.feedback_id,
                    payload.reviewer,
                    created_at,
                    now,
                    expires_at,
                ),
            )
        return self.get(record_id)

    def get(self, override_id: str) -> OverrideRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM fact_overrides WHERE id = ?", (override_id,)
            ).fetchone()
        if not row:
            raise KeyError(override_id)
        return _record(row)

    def list(
        self, company_id: str | None = None, include_expired: bool = True
    ) -> list[OverrideRecord]:
        query = "SELECT * FROM fact_overrides"
        params: list[Any] = []
        clauses: list[str] = []
        if company_id:
            clauses.append("company_id = ?")
            params.append(company_id)
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_now())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY company_id, field"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_record(row) for row in rows]

    def delete(self, override_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM fact_overrides WHERE id = ?", (override_id,)
            )
            return cursor.rowcount > 0

    def stats(self) -> dict[str, Any]:
        rows = self.list()
        active = [row for row in rows if not row.is_expired]
        return {
            "total": len(rows),
            "active": len(active),
            "expired": len(rows) - len(active),
            "companies": len({row.company_id for row in active}),
            "fromFeedback": len([row for row in active if row.feedback_id]),
        }

    def apply(self, payload: dict, company_id: str) -> dict:
        """Patch a company ESG payload in place with this company's live
        overrides, and record what was changed under `overrides` so the model can
        say the figure is a reviewer correction rather than an engine output."""
        applied: list[dict[str, Any]] = []
        for row in self.list(company_id=company_id, include_expired=False):
            previous = _read_path(payload, row.field)
            if not _write_path(payload, row.field, row.value):
                continue
            applied.append(
                {
                    "field": row.field,
                    "label": row.field_label,
                    "value": row.value,
                    "engine_value": previous,
                    "note": row.note,
                    "source_url": row.source_url,
                    "reviewer": row.reviewer,
                    "corrected_at": row.updated_at,
                }
            )
        if applied:
            payload["overrides"] = applied
            payload["overrides_note"] = (
                "A human reviewer corrected the fields listed in `overrides`. Those "
                "values replace the engine's output and are authoritative — use them "
                "and do not cite the superseded `engine_value`."
            )
        return payload


def _read_path(payload: dict, field: str) -> Any:
    node: Any = payload
    for part in field.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _write_path(payload: dict, field: str, value: Any) -> bool:
    parts = field.split(".")
    node: Any = payload
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    if not isinstance(node, dict):
        return False
    node[parts[-1]] = value
    return True


def _record(row: sqlite3.Row) -> OverrideRecord:
    field = row["field"]
    spec = OVERRIDABLE_FIELDS.get(field, {})
    expires_at = row["expires_at"]
    return OverrideRecord(
        id=row["id"],
        company_id=row["company_id"],
        field=field,
        field_label=spec.get("label", field),
        value=_load(row["value_json"]),
        note=row["note"],
        source_url=row["source_url"],
        feedback_id=row["feedback_id"],
        reviewer=row["reviewer"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=expires_at,
        is_expired=bool(expires_at and expires_at <= _now()),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
