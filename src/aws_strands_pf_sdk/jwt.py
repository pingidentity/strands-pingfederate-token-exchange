"""Helpers for decoding unverified JWT claims."""

from __future__ import annotations

import base64
import json
from typing import Any


def decode_unverified_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JWT payload without validating the signature."""

    parts = token.split(".")
    if len(parts) != 3:
        return {}

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
        decoded = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        return {}

    return decoded if isinstance(decoded, dict) else {}


def get_jwt_subject(token: str) -> str:
    """Return the `sub` claim when present."""

    subject = decode_unverified_jwt_payload(token).get("sub", "")
    return str(subject).strip() if subject else ""


def get_jwt_scopes(token: str) -> tuple[str, ...]:
    """Return scopes from a `scope` or `scp` claim."""

    payload = decode_unverified_jwt_payload(token)
    claim = payload.get("scope", payload.get("scp"))
    if isinstance(claim, str):
        return tuple(scope for scope in claim.split() if scope)
    if isinstance(claim, list):
        return tuple(str(scope).strip() for scope in claim if str(scope).strip())
    return ()
