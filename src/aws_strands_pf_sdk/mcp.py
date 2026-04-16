"""Helpers for wiring PingFederate token exchange into Strands MCP clients."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Sequence

import httpx
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

from .config import MCPServerConfig, PingFederateSettings
from .errors import ConfigurationError
from .jwt import get_jwt_scopes, get_jwt_subject
from .scopes import resolve_exchange_scopes
from .token_exchange import PingFederateTokenExchangeClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _CachedToken:
    access_token: str
    expires_at: float


class ExchangedTokenCache:
    """Simple per-invocation cache for downstream access tokens."""

    def __init__(self, *, safety_window_seconds: int = 30) -> None:
        self._safety_window_seconds = safety_window_seconds
        self._cache: dict[tuple[str, str, str], _CachedToken] = {}

    def get(
        self,
        *,
        subject_sub: str,
        audience: str,
        scope_key: str,
    ) -> str | None:
        cached = self._cache.get((subject_sub, audience, scope_key))
        if cached is None:
            return None
        if cached.expires_at <= time.time():
            self._cache.pop((subject_sub, audience, scope_key), None)
            return None
        return cached.access_token

    def put(
        self,
        *,
        subject_sub: str,
        audience: str,
        scope_key: str,
        access_token: str,
        expires_in: int | None,
    ) -> None:
        ttl = max((expires_in or 300) - self._safety_window_seconds, 0)
        self._cache[(subject_sub, audience, scope_key)] = _CachedToken(
            access_token=access_token,
            expires_at=time.time() + ttl,
        )


class _ToolCallAuth(httpx.Auth):
    """Inject a PingFederate-exchanged token only for MCP `tools/call` requests."""

    def __init__(
        self,
        *,
        subject_token: str,
        subject_sub: str,
        subject_scopes: tuple[str, ...],
        server_config: MCPServerConfig,
        settings: PingFederateSettings,
        cache: ExchangedTokenCache,
        exchange_client: PingFederateTokenExchangeClient,
    ) -> None:
        self._subject_token = subject_token
        self._subject_sub = subject_sub
        self._subject_scopes = subject_scopes
        self._server_config = server_config
        self._settings = settings
        self._cache = cache
        self._exchange_client = exchange_client

    def auth_flow(self, request: httpx.Request):
        if not self._is_tool_call(request):
            yield request
            return

        audience = self._server_config.audience or self._server_config.url
        scopes = resolve_exchange_scopes(
            self._subject_scopes,
            scope_prefix=self._server_config.scope_prefix,
            default_scopes=self._server_config.default_scopes,
            prefix_to_strip=self._settings.incoming_scope_prefix_to_strip,
        )
        scope_key = " ".join(scopes)
        cached_token = self._cache.get(
            subject_sub=self._subject_sub,
            audience=audience,
            scope_key=scope_key,
        )
        if cached_token is None:
            exchange_result = self._exchange_client.exchange_token(
                self._subject_token,
                audience=audience,
                scopes=scopes,
            )
            cached_token = exchange_result.access_token
            self._cache.put(
                subject_sub=self._subject_sub,
                audience=audience,
                scope_key=scope_key,
                access_token=exchange_result.access_token,
                expires_in=exchange_result.expires_in,
            )
            LOGGER.debug(
                "Exchanged token for server=%s audience=%s scopes=%s",
                self._server_config.name,
                audience,
                scope_key,
            )

        request.headers["Authorization"] = f"Bearer {cached_token}"
        yield request

    @staticmethod
    def _is_tool_call(request: httpx.Request) -> bool:
        if not request.content:
            return False
        try:
            payload = json.loads(request.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return payload.get("method") == "tools/call"


def create_mcp_clients(
    *,
    subject_token: str,
    server_configs: Sequence[MCPServerConfig],
    settings: PingFederateSettings,
) -> list[MCPClient]:
    """Create Strands MCP clients that exchange tokens on demand."""

    subject_sub = get_jwt_subject(subject_token)
    subject_scopes = get_jwt_scopes(subject_token)
    cache = ExchangedTokenCache()
    exchange_client = PingFederateTokenExchangeClient(settings)

    clients: list[MCPClient] = []
    for server_config in server_configs:
        if server_config.transport != "streamable_http":
            raise ConfigurationError(
                f"Server '{server_config.name}' uses unsupported transport '{server_config.transport}'. "
                "Only 'streamable_http' is supported."
            )

        auth = _ToolCallAuth(
            subject_token=subject_token,
            subject_sub=subject_sub,
            subject_scopes=subject_scopes,
            server_config=server_config,
            settings=settings,
            cache=cache,
            exchange_client=exchange_client,
        )
        verify_ssl = server_config.verify_ssl
        client = MCPClient(
            lambda url=server_config.url, verify=verify_ssl, auth_handler=auth: streamablehttp_client(
                url,
                auth=auth_handler,
                httpx_client_factory=lambda **kwargs: httpx.AsyncClient(
                    **{**kwargs, "verify": verify}
                ),
            )
        )
        clients.append(client)

    return clients
