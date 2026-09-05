from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent import AssistantResponse, ChatMessage


ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_CHAT_HISTORY_DB = ROOT / "backend" / "data" / "chat_history.sqlite3"
_RUNTIME_DATA_DIR = Path(
    os.environ.get("POLYFINTECH_DATA_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or _BUNDLED_CHAT_HISTORY_DB.parent
).expanduser()
DEFAULT_CHAT_HISTORY_DB = Path(
    os.environ.get("CHAT_HISTORY_DB_PATH")
    or (_RUNTIME_DATA_DIR / "chat_history.sqlite3")
).expanduser()

LEGACY_SHOWCASE_SESSION_IDS = (
    "session-8476fde81c0142aeb60fb86cdbab95f4",
    "session-8b8382a7147a45e69a893a320b9b3878",
    "session-768c3a0945b74d9d954657f8dc91b118",
    "session-766ebd0c5c514023ada3e3d95c59a5bb",
    "session-77b97f00f4c1447ea380ea5724de7748",
    "session-6ee9c3afadad487a84978b8a72e863d5",
    "session-46c66ce525144b41b0f0287619ac862c",
    "session-c8215663231240b6bf63bbd7836c272f",
    "session-4f885f9ba921404e89bef0e12108f219",
    "session-e295c3eafd7d4c94b9a79980394f99f1",
    "session-19f4821f248a4bdfa2b9ae8d456a24ef",
    "session-e7bf473f0704406f8d269d9fd8fb9940",
)

SHOWCASE_CHATS: tuple[dict[str, Any], ...] = (
    {
        "id": "session-showcase-report",
        "age_minutes": 5,
        "title": "Generate a Sembcorp ESG investment report",
        "prompt": (
            "Generate an investment-grade ESG report for Sembcorp Industries using "
            "the current dashboard evidence and latest scraped disclosures."
        ),
        "response": """## Sembcorp Industries ESG report

The report is ready. It combines the current evidence engine, the rating outlook, transition targets, regulatory coverage, and source-linked company disclosures.

### Executive view

- **ESG consensus:** 81.7 / 100
- **Evidence score:** 80.0 / 100 with 60.3% confidence
- **2026 rating outlook:** AA, likely hold
- **Transition signal:** renewables capacity reached 15 GW in 2025 against a 25 GW target for 2028
- **Watchpoint:** Sembcorp expects near-term emissions to rise following the Alinta Energy acquisition and has updated its emissions-intensity pathway

Open the report artifact below to preview it or download it as a PDF.""",
        "sources": [
            {
                "title": "Sembcorp Sustainability Report 2025",
                "url": "https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf",
                "snippet": "2025 performance, climate targets, and material ESG disclosures.",
                "source": "bright_data+pdf",
            },
            {
                "title": "Sembcorp Climate Action Plan",
                "url": "https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/",
                "snippet": "Current renewable-capacity, emissions-intensity, and net-zero targets.",
                "source": "bright_data",
            },
        ],
        "tool_results": [
            {
                "name": "get_company_esg",
                "status": "ok",
                "summary": "Loaded Sembcorp's ratings, evidence pillars, forecast, and compliance signals.",
                "sourceCount": 1,
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Scraped Sembcorp's 2025 sustainability disclosures and climate targets.",
                "sourceCount": 2,
            },
        ],
        "workflow_steps": [
            {
                "label": "Loaded ESG evidence",
                "status": "ok",
                "detail": "Collected the current rating, evidence, forecast, and compliance record.",
                "toolName": "get_company_esg",
            },
            {
                "label": "Scraped current disclosures",
                "status": "ok",
                "detail": "Extracted transition targets from Sembcorp's 2025 publications.",
                "toolName": "scrape_url",
            },
            {
                "label": "Generated report",
                "status": "ok",
                "detail": "Built a source-linked ESG investment report and PDF-ready artifact.",
                "toolName": "report_generation",
            },
        ],
        "report": {
            "title": "Sembcorp Industries ESG Investment Report",
            "generatedAt": "2026-09-05T00:00:00+08:00",
            "markdown": """# Sembcorp Industries ESG Investment Report

## Executive summary

Sembcorp Industries combines a strong current ESG consensus with high evidence coverage and a credible renewable-growth programme. The current rating outlook is AA and likely to hold. The central investment tension is between rapid renewable deployment and the near-term emissions effect of a larger thermal portfolio following the Alinta Energy acquisition.

## Current ESG position

| Measure | Current view |
|---|---:|
| ESG consensus | 81.7 / 100 |
| Evidence score | 80.0 / 100 |
| Evidence confidence | 60.3% |
| Environmental pillar | 80.0 / 100 |
| Social pillar | 100.0 / 100 |
| Governance pillar | 50.0 / 100 |
| 2026 rating outlook | AA, likely hold |

The evidence engine shows broad disclosure coverage, with water management remaining the principal uncovered material topic in the current record.

## Transition plan

Sembcorp reported 15 GW of gross installed renewable capacity at the end of 2025 and targets 25 GW by 2028. Its updated climate pathway targets emissions intensity of 0.26 tCO2e/MWh by 2035 and net-zero Scope 1 and 2 emissions by 2050.

The company also states that emissions are expected to increase in the near term following the Alinta Energy acquisition. This makes delivery against the revised intensity pathway a key monitoring point.

## Investment interpretation

**Strengths:** high peer-relative ESG consensus, strong environmental and social evidence, expanding renewable capacity, and source-linked transition targets.

**Risks:** governance evidence trails the other pillars, transition execution must absorb a larger thermal portfolio, and evidence confidence is not yet high enough to treat every disclosure as independently verified.

## Monitoring checklist

1. Progress from 15 GW toward the 25 GW renewable-capacity target.
2. Movement in group emissions intensity following the Alinta consolidation.
3. New evidence on water management and governance controls.
4. Any change to the AA rating baseline or evidence confidence.

## Sources

- [Sembcorp Sustainability Report 2025](https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf)
- [Sembcorp Climate Action Plan](https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/)
""",
        },
    },
    {
        "id": "session-showcase-prediction",
        "age_minutes": 12,
        "title": "Sembcorp's likely ESG score from current news",
        "prompt": (
            "What is the current ESG score likely to be for Sembcorp, "
            "based on its current news?"
        ),
        "response": """**Likely score: 80.0 / 100 — unchanged by the current news.**

The news flow is mildly negative: **14 headlines, 8 controversy against 3 positive**. The drag is a missed sustainability target; the support is a $10.5bn energy-transition programme.

That does not move the score. News tells us where to look, but credit only changes when a claim is verified against evidence — and nothing here has been yet. It does flag where the exposure sits: Governance is the weakest pillar at 50.0, and a missed target lands there.

For context, the rater consensus is 69.4 against our 80.0, on a peer median of 52.8. Confidence is 60.3%, so read this as a direction, not a decimal.

**What would actually move it:** a verified emissions figure for this year, or governance disclosure on the missed target.""",
        "sources": [
            {
                "title": "Sembcorp Sustainability Report 2025",
                "url": "https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf",
                "snippet": "Current climate performance and targets.",
                "source": "bright_data+pdf",
            },
            {
                "title": "Current Sembcorp ESG news — 14 headlines",
                "url": "https://www.sembcorp.com/en/media/media-releases/",
                "snippet": "8 controversy, 3 positive, net sentiment -5 in the current window.",
                "source": "gdelt",
            },
        ],
        "tool_results": [
            {
                "name": "research_company_esg_news",
                "status": "ok",
                "summary": "Collected 14 current Sembcorp headlines — 8 controversy, 3 positive, net sentiment -5.",
                "sourceCount": 14,
            },
            {
                "name": "get_company_esg",
                "status": "ok",
                "summary": "Loaded Sembcorp's evidence score, pillar split, confidence, and rater consensus.",
                "sourceCount": 1,
            },
        ],
        "workflow_steps": [
            {
                "label": "Read the current news",
                "status": "ok",
                "detail": "Pulled 14 headlines and classified each as controversy, positive, or neutral.",
                "toolName": "research_company_esg_news",
            },
            {
                "label": "Loaded company evidence",
                "status": "ok",
                "detail": "Resolved Sembcorp's evidence score, pillar evidence, and confidence.",
                "toolName": "get_company_esg",
            },
            {
                "label": "Tested the news against the score",
                "status": "ok",
                "detail": "No headline corroborates a new claim yet, so credit is unchanged at 80.0.",
                "toolName": "get_company_esg",
            },
        ],
        "report": None,
    },
    {
        "id": "session-showcase-web-scrape",
        "age_minutes": 20,
        "title": "Scrape Sembcorp's transition targets",
        "prompt": (
            "Scrape Sembcorp Industries' latest sustainability disclosures and "
            "extract its transition targets with source links."
        ),
        "response": """## Sembcorp transition-target scan

I searched the current company disclosures and scraped the FY2025 sustainability materials.

| Metric | 2025 position | Current target |
|---|---:|---:|
| Gross installed renewable capacity | 15 GW | 25 GW by 2028 |
| GHG emissions intensity | 0.21 tCO2e/MWh | 0.26 tCO2e/MWh by 2035 |
| Scope 1 and 2 net zero | In transition | Net zero by 2050 |

### Material update

Sembcorp says the Alinta Energy acquisition will increase emissions in the near term before they decline. The company consequently updated its emissions-intensity pathway while retaining the 25 GW renewables target and 2050 net-zero goal.

### Sources

- [Sustainability Report 2025](https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf)
- [Climate Action Plan](https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/)""",
        "sources": [
            {
                "title": "Sembcorp Sustainability Report 2025",
                "url": "https://www.sembcorp.com/media/z4ohu5lz/sembcorp-ar25_sustainability-report.pdf",
                "snippet": "15 GW installed renewables in 2025 and a 25 GW target for 2028.",
                "source": "bright_data+pdf",
            },
            {
                "title": "Sembcorp Climate Action Plan",
                "url": "https://www.sembcorp.com/driving-energy-transition/our-approach-to-sustainability/climate-action-plan/",
                "snippet": "Updated 2035 emissions-intensity and 2050 net-zero targets.",
                "source": "bright_data",
            },
        ],
        "tool_results": [
            {
                "name": "web_search",
                "status": "ok",
                "summary": "Found Sembcorp's current sustainability report and climate action page.",
                "sourceCount": 2,
            },
            {
                "name": "scrape_url",
                "status": "ok",
                "summary": "Extracted current capacity, emissions-intensity, and net-zero targets.",
                "sourceCount": 2,
            },
        ],
        "workflow_steps": [
            {
                "label": "Searched the web",
                "status": "ok",
                "detail": "Located the latest first-party sustainability disclosures.",
                "toolName": "web_search",
            },
            {
                "label": "Scraped source pages",
                "status": "ok",
                "detail": "Extracted transition targets and the latest material update.",
                "toolName": "scrape_url",
            },
        ],
        "report": None,
    },
)


def _seed_runtime_chat_history() -> None:
    if (
        DEFAULT_CHAT_HISTORY_DB != _BUNDLED_CHAT_HISTORY_DB
        and not DEFAULT_CHAT_HISTORY_DB.exists()
        and _BUNDLED_CHAT_HISTORY_DB.exists()
    ):
        DEFAULT_CHAT_HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_BUNDLED_CHAT_HISTORY_DB, DEFAULT_CHAT_HISTORY_DB)


_seed_runtime_chat_history()


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
    def __init__(
        self,
        path: Path | str = DEFAULT_CHAT_HISTORY_DB,
        *,
        curate_showcase: bool | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        should_curate = (
            self.path.resolve() == DEFAULT_CHAT_HISTORY_DB.resolve()
            if curate_showcase is None
            else curate_showcase
        )
        if should_curate:
            self._curate_showcase_history()

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

    def _curate_showcase_history(self) -> None:
        # The curated chats are content, and this module is their only source of truth, so
        # the current ones are dropped and rebuilt on every boot alongside the retired ids.
        # Without this the INSERTs below are OR IGNORE against rows that already exist on
        # the deployed volume, and an edited prompt or answer would never reach production.
        stale_ids = LEGACY_SHOWCASE_SESSION_IDS + tuple(
            chat["id"] for chat in SHOWCASE_CHATS
        )
        placeholders = ",".join("?" for _ in stale_ids)
        now = datetime.now(timezone.utc)

        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})",
                stale_ids,
            )
            connection.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders})",
                stale_ids,
            )

            for chat in SHOWCASE_CHATS:
                created_at = now - timedelta(minutes=chat["age_minutes"])
                updated_at = created_at + timedelta(minutes=1)
                page_context = {
                    "route": "assistant",
                    "showcase": True,
                    "capability": chat["id"].removeprefix("session-showcase-"),
                    "company": {
                        "id": "U96",
                        "name": "Sembcorp Industries",
                        "ticker": "U96.SI",
                    },
                }
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_sessions (
                        id, title, created_at, updated_at, page_context_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chat["id"],
                        chat["title"],
                        created_at.isoformat(),
                        updated_at.isoformat(),
                        json_dump(page_context),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_messages (
                        id, session_id, role, content, created_at,
                        sources_json, reference_articles_json, tool_results_json,
                        workflow_steps_json, report_json, model, page_context_json
                    ) VALUES (?, ?, 'user', ?, ?, '[]', '[]', '[]', '[]',
                              NULL, NULL, ?)
                    """,
                    (
                        f"msg-{chat['id']}-prompt",
                        chat["id"],
                        chat["prompt"],
                        created_at.isoformat(),
                        json_dump(page_context),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_messages (
                        id, session_id, role, content, created_at,
                        sources_json, reference_articles_json, tool_results_json,
                        workflow_steps_json, report_json, model, page_context_json
                    ) VALUES (?, ?, 'assistant', ?, ?, ?, '[]', ?, ?, ?, ?, ?)
                    """,
                    (
                        f"msg-{chat['id']}-response",
                        chat["id"],
                        chat["response"],
                        updated_at.isoformat(),
                        json_dump(chat["sources"]),
                        json_dump(chat["tool_results"]),
                        json_dump(chat["workflow_steps"]),
                        json_dump(chat["report"]) if chat["report"] else None,
                        "PolyFintech ESG agent",
                        json_dump(page_context),
                    ),
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
