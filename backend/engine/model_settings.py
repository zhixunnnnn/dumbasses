"""Which LLM provider and model the research agent runs on.

Selection is persisted (non-secret) in `app_settings`; credentials are only ever
read from the environment, so the Settings page never receives a key.

Two providers are wired:
  * ``openrouter`` — live today; the model id is switchable from Settings.
  * ``bedrock``    — Amazon Bedrock. The settings, credential detection, and the
    adapter seam are in place; ``build_bedrock_chat_model`` is the single
    placeholder left to fill in (see backend/app/agent.py for where it is used).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .db import bootstrap

SETTINGS_KEY = "models"
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"
DEFAULT_BEDROCK_REGION = "us-east-1"

PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "bedrock": "Amazon Bedrock",
}

# Curated, known-good ids so the picker is usable without leaving the page. Any
# other id can still be typed in; it is passed through unchanged.
OPENROUTER_MODELS = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-chat",
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
]
BEDROCK_MODELS = [
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "amazon.nova-pro-v1:0",
    "meta.llama3-3-70b-instruct-v1:0",
]
BEDROCK_REGIONS = [
    "us-east-1",
    "us-west-2",
    "eu-central-1",
    "ap-southeast-1",
    "ap-northeast-1",
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "openrouter",
    "openrouterModel": DEFAULT_OPENROUTER_MODEL,
    "bedrockModelId": DEFAULT_BEDROCK_MODEL,
    "bedrockRegion": DEFAULT_BEDROCK_REGION,
    "temperature": 0.25,
    "maxTokens": 1800,
}


def get_model_settings() -> dict[str, Any]:
    conn = bootstrap()
    try:
        row = conn.execute(
            "SELECT value_json, updated_at FROM app_settings WHERE key=?",
            (SETTINGS_KEY,),
        ).fetchone()
    finally:
        conn.close()
    stored = json.loads(row["value_json"]) if row else {}
    settings = {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}
    settings["updatedAt"] = row["updated_at"] if row else None
    settings["providerStatus"] = provider_status(settings["provider"])
    settings["catalog"] = {
        "openrouterModels": OPENROUTER_MODELS,
        "bedrockModels": BEDROCK_MODELS,
        "bedrockRegions": BEDROCK_REGIONS,
    }
    return settings


def save_model_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_model_settings()
    combined = {key: current[key] for key in DEFAULT_SETTINGS}
    combined.update({k: v for k, v in payload.items() if k in DEFAULT_SETTINGS and v is not None})
    settings = _validate(combined)
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
            (
                SETTINGS_KEY,
                json.dumps(settings, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_model_settings()


def active_model() -> dict[str, Any]:
    """The provider/model the agent should use for the next request. Falls back to
    OpenRouter if the selected provider has no credentials, so a half-configured
    Bedrock switch never takes the assistant offline."""
    settings = get_model_settings()
    provider = settings["provider"]
    status = settings["providerStatus"]
    fallback_reason = None
    if not status[provider]["available"]:
        fallback_reason = status[provider]["reason"]
        provider = "openrouter"
    return {
        "provider": provider,
        "model": (
            settings["openrouterModel"]
            if provider == "openrouter"
            else settings["bedrockModelId"]
        ),
        "region": settings["bedrockRegion"],
        "temperature": float(settings["temperature"]),
        "maxTokens": int(settings["maxTokens"]),
        "requestedProvider": settings["provider"],
        "fallbackReason": fallback_reason,
    }


def provider_status(selected: str) -> dict[str, dict[str, Any]]:
    openrouter_ready = bool(os.environ.get("OPENROUTER_API_KEY"))
    bedrock_ready, bedrock_reason = _bedrock_credentials()
    statuses = {
        "openrouter": (
            openrouter_ready,
            None if openrouter_ready else "OPENROUTER_API_KEY is missing.",
        ),
        "bedrock": (bedrock_ready, bedrock_reason),
    }
    return {
        key: {
            "id": key,
            "label": PROVIDER_LABELS[key],
            "available": available,
            "reason": reason,
            "selected": key == selected,
            "implemented": key == "openrouter",
        }
        for key, (available, reason) in statuses.items()
    }


def _bedrock_credentials() -> tuple[bool, str | None]:
    """Bedrock accepts either a bearer token or standard SigV4 credentials (the
    latter also come from an instance/task role, which we cannot see from env)."""
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        return True, None
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True, None
    return False, (
        "Set AWS_BEARER_TOKEN_BEDROCK, or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY."
    )


def build_bedrock_chat_model(model_id: str, region: str, temperature: float, max_tokens: int):
    """PLACEHOLDER — Amazon Bedrock chat model for the LangChain agent.

    To finish the integration:
      1. add ``langchain-aws`` and ``boto3`` to backend/requirements.txt
      2. set AWS_BEARER_TOKEN_BEDROCK (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
         plus AWS_REGION on the deployment
      3. replace the body below with:

             from langchain_aws import ChatBedrockConverse

             return ChatBedrockConverse(
                 model=model_id,
                 region_name=region,
                 temperature=temperature,
                 max_tokens=max_tokens,
             )

    The Converse API is the right entry point here because the agent relies on
    tool-calling, which Bedrock exposes uniformly through Converse across model
    families. Everything else — settings, credential detection, provider
    switching, and the OpenRouter fallback in ``active_model`` — is already wired.
    """
    raise NotImplementedError(
        "Amazon Bedrock is selected but the adapter is still a placeholder. "
        "See backend/engine/model_settings.build_bedrock_chat_model for the "
        "three steps needed to enable it. The assistant is falling back to "
        "OpenRouter in the meantime."
    )


def _validate(settings: dict[str, Any]) -> dict[str, Any]:
    if settings["provider"] not in PROVIDER_LABELS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDER_LABELS)}")
    for key in ("openrouterModel", "bedrockModelId", "bedrockRegion"):
        value = str(settings[key] or "").strip()
        if not value:
            raise ValueError(f"{key} must not be empty")
        settings[key] = value
    temperature = float(settings["temperature"])
    if not 0.0 <= temperature <= 2.0:
        raise ValueError("temperature must be between 0 and 2")
    settings["temperature"] = round(temperature, 2)
    max_tokens = int(settings["maxTokens"])
    if not 256 <= max_tokens <= 8192:
        raise ValueError("maxTokens must be between 256 and 8192")
    settings["maxTokens"] = max_tokens
    return settings
