"""PingFederate RFC 8693 token exchange client."""

from __future__ import annotations

import base64
import json
import ssl
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import parse, request

from .config import PingFederateSettings
from .errors import TokenExchangeError


def _coerce_expires_in(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class TokenExchangeResult:
    """Parsed token exchange response."""

    access_token: str
    token_type: str
    expires_in: int | None
    scope: str | None
    issued_token_type: str | None
    payload: dict[str, Any]


class PingFederateTokenExchangeClient:
    """Small client for PingFederate OAuth 2.0 token exchange."""

    def __init__(
        self,
        settings: PingFederateSettings,
        *,
        urlopen: Callable[..., Any] = request.urlopen,
    ) -> None:
        self._settings = settings
        self._urlopen = urlopen

    def exchange_token(
        self,
        subject_token: str,
        *,
        audience: str | None = None,
        scopes: tuple[str, ...] = (),
        actor_token: str | None = None,
        actor_token_type: str | None = None,
    ) -> TokenExchangeResult:
        """Exchange the inbound subject token for a downstream access token."""

        form_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "subject_token_type": self._settings.subject_token_type,
        }

        if self._settings.requested_token_type:
            form_data["requested_token_type"] = self._settings.requested_token_type
        if audience:
            form_data[self._settings.audience_parameter] = audience
        scope_value = " ".join(scopes) if scopes else None
        if scope_value:
            form_data["scope"] = scope_value
        if actor_token:
            form_data["actor_token"] = actor_token
            form_data["actor_token_type"] = actor_token_type or "urn:ietf:params:oauth:token-type:access_token"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if self._settings.client_auth_method == "client_secret_basic":
            credentials = f"{self._settings.client_id}:{self._settings.client_secret}".encode("utf-8")
            basic_auth = base64.b64encode(credentials).decode("ascii")
            headers["Authorization"] = f"Basic {basic_auth}"
        else:
            form_data["client_id"] = self._settings.client_id
            form_data["client_secret"] = self._settings.client_secret

        encoded_body = parse.urlencode(form_data).encode("utf-8")
        http_request = request.Request(
            self._settings.token_endpoint,
            data=encoded_body,
            headers=headers,
            method="POST",
        )
        ssl_context = self._build_ssl_context()

        try:
            with self._urlopen(
                http_request,
                timeout=self._settings.request_timeout_seconds,
                context=ssl_context,
            ) as response:
                raw_body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            self._raise_exchange_error(exc.code, body)
            raise AssertionError("unreachable")
        except urllib_error.URLError as exc:
            raise TokenExchangeError(
                status_code=0,
                error="request_failed",
                description=str(exc.reason),
            ) from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise TokenExchangeError(
                status_code=502,
                error="invalid_response",
                description="Token exchange endpoint returned non-JSON output",
            ) from exc

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise TokenExchangeError(
                status_code=502,
                error="invalid_response",
                description="Token exchange response did not contain an access_token",
            )

        expires_in = payload.get("expires_in")
        return TokenExchangeResult(
            access_token=access_token,
            token_type=str(payload.get("token_type", "Bearer")),
            expires_in=_coerce_expires_in(expires_in),
            scope=str(payload.get("scope")) if payload.get("scope") is not None else None,
            issued_token_type=(
                str(payload.get("issued_token_type"))
                if payload.get("issued_token_type") is not None
                else None
            ),
            payload=payload,
        )

    def _build_ssl_context(self) -> ssl.SSLContext:
        if self._settings.verify_ssl:
            return ssl.create_default_context()
        return ssl._create_unverified_context()

    def _raise_exchange_error(self, status_code: int, body: str) -> None:
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        raise TokenExchangeError(
            status_code=status_code,
            error=str(payload.get("error", "token_exchange_failed")),
            description=str(payload.get("error_description", body)),
        )
