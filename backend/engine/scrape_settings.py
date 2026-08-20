"""Persistent, non-secret settings for scheduled and agent-triggered scraping."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .db import bootstrap
from .scraper_providers import PROVIDER_LABELS, provider_availability

SETTINGS_KEY = "scraping"
DEFAULT_SETTINGS: dict[str, Any] = {
    "providers": {
        "brightdata": True,
        "scrapedo": False,
        "oxylabs": False,
        "crawl4ai_searxng": False,
    },
    "sourceTypes": {
        "verified": True,
        "nonVerified": True,
        "community": True,
    },
    "frequency": "weekly",
    "maxCompanies": 10,
    "timezone": "Asia/Singapore",
    "runAt": "06:00",
    "retainRawDays": 30,
    "adaptiveCrawl": True,
    "communitySentimentWeight": 0.02,
}


def get_scrape_settings() -> dict[str, Any]:
    conn = bootstrap()
    try:
        row = conn.execute(
            "SELECT value_json, updated_at FROM app_settings WHERE key=?",
            (SETTINGS_KEY,),
        ).fetchone()
    finally:
        conn.close()
    stored = json.loads(row["value_json"]) if row else {}
    settings = _merge_settings(stored)
    settings["updatedAt"] = row["updated_at"] if row else None
    settings["providerStatus"] = _provider_status(settings["providers"])
    return settings


def save_scrape_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_scrape_settings()
    combined = {
        key: current.get(key, value)
        for key, value in DEFAULT_SETTINGS.items()
    }
    combined.update({key: value for key, value in payload.items() if key != "providers"})
    if isinstance(payload.get("providers"), dict):
        combined["providers"] = {
            **current["providers"],
            **payload["providers"],
        }
    if isinstance(payload.get("sourceTypes"), dict):
        combined["sourceTypes"] = {
            **current["sourceTypes"],
            **payload["sourceTypes"],
        }
    settings = _validate_settings(_merge_settings(combined))
    persisted = {key: value for key, value in settings.items() if key not in {"updatedAt", "providerStatus"}}
    updated_at = datetime.now(timezone.utc).isoformat()
    conn = bootstrap()
    try:
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=excluded.updated_at
            """,
            (SETTINGS_KEY, json.dumps(persisted, separators=(",", ":")), updated_at),
        )
        conn.commit()
    finally:
        conn.close()
    return get_scrape_settings()


def enabled_providers() -> list[str]:
    settings = get_scrape_settings()
    return [
        provider_id
        for provider_id, enabled in settings["providers"].items()
        if enabled and settings["providerStatus"][provider_id]["available"]
    ]


def _merge_settings(payload: dict[str, Any]) -> dict[str, Any]:
    providers = dict(DEFAULT_SETTINGS["providers"])
    incoming_providers = payload.get("providers")
    if isinstance(incoming_providers, dict):
        for key in providers:
            if key in incoming_providers:
                providers[key] = bool(incoming_providers[key])
    merged = dict(DEFAULT_SETTINGS)
    merged.update({key: value for key, value in payload.items() if key in DEFAULT_SETTINGS})
    merged["providers"] = providers
    source_types = dict(DEFAULT_SETTINGS["sourceTypes"])
    incoming_source_types = payload.get("sourceTypes")
    if isinstance(incoming_source_types, dict):
        for key in source_types:
            if key in incoming_source_types:
                source_types[key] = bool(incoming_source_types[key])
    merged["sourceTypes"] = source_types
    return merged


def _validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    if settings["frequency"] not in {"daily", "weekly", "monthly"}:
        raise ValueError("frequency must be daily, weekly, or monthly")
    if settings["timezone"] != "Asia/Singapore":
        raise ValueError("Only Asia/Singapore is currently supported")
    if not isinstance(settings["runAt"], str) or len(settings["runAt"].split(":")) != 2:
        raise ValueError("runAt must use HH:MM format")
    max_companies = int(settings["maxCompanies"])
    if max_companies < 1 or max_companies > 50:
        raise ValueError("maxCompanies must be between 1 and 50")
    settings["maxCompanies"] = max_companies
    retain_days = int(settings["retainRawDays"])
    if retain_days < 1 or retain_days > 365:
        raise ValueError("retainRawDays must be between 1 and 365")
    settings["retainRawDays"] = retain_days
    settings["communitySentimentWeight"] = 0.02
    settings["adaptiveCrawl"] = True
    return settings


def _provider_status(enabled: dict[str, bool]) -> dict[str, dict[str, Any]]:
    availability = provider_availability()
    return {
        key: {
            **availability[key],
            "label": PROVIDER_LABELS[key],
            "enabled": bool(enabled.get(key)),
        }
        for key in PROVIDER_LABELS
    }
