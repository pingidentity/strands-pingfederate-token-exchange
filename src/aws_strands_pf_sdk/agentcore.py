"""Helpers for AgentCore-style example applications."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .errors import AuthenticationError


def extract_bearer_token(value: str) -> str:
    """Parse a `Bearer <token>` header value."""

    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError("Authorization value is not a valid Bearer token")
    return parts[1].strip()


def extract_subject_token(headers: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    """Extract the inbound subject token from the request headers or body."""

    header_value = headers.get("authorization") or headers.get("Authorization")
    if header_value:
        return extract_bearer_token(str(header_value))

    payload_value = payload.get("authorization")
    if payload_value:
        return extract_bearer_token(str(payload_value))

    raise AuthenticationError(
        "Missing bearer token. Provide an Authorization header or an 'authorization' field in the JSON payload."
    )


def serialize_agent_message(message: Any) -> Any:
    """Return a JSON-serializable shape for a Strands response message."""

    if isinstance(message, (dict, list, str, int, float, bool)) or message is None:
        return message

    if hasattr(message, "model_dump"):
        return message.model_dump()

    if isinstance(message, tuple):
        return list(message)

    return {"result": str(message)}


def extract_message_text(message: Any) -> str:
    """Best-effort extraction of the primary text value from an agent message."""

    if isinstance(message, str):
        return message

    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list) and content:
            first_item = content[0]
            if isinstance(first_item, dict):
                text = first_item.get("text")
                if isinstance(text, str):
                    return text
        return json.dumps(message)

    return str(message)


def parse_scope_error_payload(message: Any) -> dict[str, Any] | None:
    """Parse the special insufficient-scope payload when the model returns it."""

    text = extract_message_text(message)
    if "insufficient_scope" not in text.lower():
        return None

    cleaned = "\n".join(line for line in text.splitlines() if "```" not in line).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
