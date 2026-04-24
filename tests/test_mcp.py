from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _install_httpx_stub():
    httpx_module = types.ModuleType("httpx")

    class Auth:
        pass

    class Request:
        def __init__(self, method: str, url: str, *, content: bytes = b"", headers=None) -> None:
            self.method = method
            self.url = url
            self.content = content
            self.headers = dict(headers or {})

    class AsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    httpx_module.Auth = Auth
    httpx_module.Request = Request
    httpx_module.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx_module
    return httpx_module


try:
    import httpx  # type: ignore
except ModuleNotFoundError:
    httpx = _install_httpx_stub()


def _install_mcp_stubs() -> None:
    if "mcp.client.streamable_http" not in sys.modules:
        mcp_module = types.ModuleType("mcp")
        client_module = types.ModuleType("mcp.client")
        streamable_http_module = types.ModuleType("mcp.client.streamable_http")

        def streamablehttp_client(url, **kwargs):
            return {"url": url, **kwargs}

        streamable_http_module.streamablehttp_client = streamablehttp_client
        mcp_module.client = client_module
        client_module.streamable_http = streamable_http_module
        sys.modules["mcp"] = mcp_module
        sys.modules["mcp.client"] = client_module
        sys.modules["mcp.client.streamable_http"] = streamable_http_module

    if "strands.tools.mcp" not in sys.modules:
        strands_module = types.ModuleType("strands")
        tools_module = types.ModuleType("strands.tools")
        strands_mcp_module = types.ModuleType("strands.tools.mcp")

        class MCPClient:
            def __init__(self, factory) -> None:
                self.factory = factory

        strands_mcp_module.MCPClient = MCPClient
        strands_module.tools = tools_module
        tools_module.mcp = strands_mcp_module
        sys.modules["strands"] = strands_module
        sys.modules["strands.tools"] = tools_module
        sys.modules["strands.tools.mcp"] = strands_mcp_module


_install_mcp_stubs()

from aws_strands_pf_sdk.config import MCPServerConfig, PingFederateSettings
from aws_strands_pf_sdk.mcp import ExchangedTokenCache, _ActorTokenProvider, _ToolCallAuth
from aws_strands_pf_sdk.token_exchange import TokenExchangeResult


class _FakeExchangeClient:
    def __init__(self, *, actor_expires_in: int = 300) -> None:
        self.actor_expires_in = actor_expires_in
        self.actor_requests: list[dict[str, object]] = []
        self.exchange_requests: list[dict[str, object]] = []

    def _client_credentials_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        scopes: tuple[str, ...] = (),
    ) -> TokenExchangeResult:
        self.actor_requests.append(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "scopes": scopes,
            }
        )
        return TokenExchangeResult(
            access_token=f"actor-token-{len(self.actor_requests)}",
            token_type="Bearer",
            expires_in=self.actor_expires_in,
            scope=" ".join(scopes) if scopes else None,
            issued_token_type=None,
            payload={},
        )

    def exchange_token(
        self,
        subject_token: str,
        *,
        audience: str | None = None,
        scopes: tuple[str, ...] = (),
        actor_token: str | None = None,
        actor_token_type: str | None = None,
    ) -> TokenExchangeResult:
        self.exchange_requests.append(
            {
                "subject_token": subject_token,
                "audience": audience,
                "scopes": scopes,
                "actor_token": actor_token,
                "actor_token_type": actor_token_type,
            }
        )
        return TokenExchangeResult(
            access_token=f"transaction-token-{len(self.exchange_requests)}",
            token_type="Bearer",
            expires_in=300,
            scope=" ".join(scopes) if scopes else None,
            issued_token_type=None,
            payload={},
        )


def _base_settings(**overrides: object) -> PingFederateSettings:
    values: dict[str, object] = {
        "token_endpoint": "https://issuer.example/as/token.oauth2",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }
    values.update(overrides)
    return PingFederateSettings(**values)


def _server_config(**overrides: object) -> MCPServerConfig:
    values: dict[str, object] = {
        "name": "search",
        "url": "https://example.com/mcp",
        "audience": "https://example.com/mcp",
        "scope_prefix": "find:domain:",
        "default_scopes": ("find:domain",),
    }
    values.update(overrides)
    return MCPServerConfig(**values)


class ExchangedTokenCacheTests(unittest.TestCase):
    def test_keeps_subject_only_and_actor_enabled_entries_separate(self) -> None:
        cache = ExchangedTokenCache(safety_window_seconds=0)
        cache.put(
            subject_sub="user-123",
            audience="https://example.com/mcp",
            scope_key="find:domain:read",
            actor_mode="subject_only",
            access_token="subject-only-token",
            expires_in=300,
        )
        cache.put(
            subject_sub="user-123",
            audience="https://example.com/mcp",
            scope_key="find:domain:read",
            actor_mode="actor_enabled",
            access_token="actor-backed-token",
            expires_in=300,
        )

        self.assertEqual(
            cache.get(
                subject_sub="user-123",
                audience="https://example.com/mcp",
                scope_key="find:domain:read",
                actor_mode="subject_only",
            ),
            "subject-only-token",
        )
        self.assertEqual(
            cache.get(
                subject_sub="user-123",
                audience="https://example.com/mcp",
                scope_key="find:domain:read",
                actor_mode="actor_enabled",
            ),
            "actor-backed-token",
        )


class ActorTokenProviderTests(unittest.TestCase):
    def test_returns_none_when_actor_support_is_disabled(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings()
        provider = _ActorTokenProvider(
            settings=settings,
            exchange_client=fake_exchange_client,
        )

        self.assertEqual(provider.cache_key, "subject_only")
        self.assertIsNone(provider.get_token())
        self.assertEqual(fake_exchange_client.actor_requests, [])

    def test_reuses_cached_actor_token_until_expiry(self) -> None:
        fake_exchange_client = _FakeExchangeClient(actor_expires_in=300)
        settings = _base_settings(
            enable_actor_token=True,
            actor_client_id="actor-client-id",
            actor_client_secret="actor-client-secret",
            actor_scopes=("mcp:invoke",),
        )
        provider = _ActorTokenProvider(
            settings=settings,
            exchange_client=fake_exchange_client,
            safety_window_seconds=0,
        )

        first_token = provider.get_token()
        second_token = provider.get_token()

        self.assertEqual(first_token, "actor-token-1")
        self.assertEqual(second_token, "actor-token-1")
        self.assertEqual(len(fake_exchange_client.actor_requests), 1)

    def test_refreshes_expired_actor_token(self) -> None:
        fake_exchange_client = _FakeExchangeClient(actor_expires_in=1)
        settings = _base_settings(
            enable_actor_token=True,
            actor_client_id="actor-client-id",
            actor_client_secret="actor-client-secret",
        )
        provider = _ActorTokenProvider(
            settings=settings,
            exchange_client=fake_exchange_client,
            safety_window_seconds=0,
        )

        with mock.patch("aws_strands_pf_sdk.mcp.time.time", side_effect=[100.0, 102.0, 102.0]):
            first_token = provider.get_token()
            second_token = provider.get_token()

        self.assertEqual(first_token, "actor-token-1")
        self.assertEqual(second_token, "actor-token-2")
        self.assertEqual(len(fake_exchange_client.actor_requests), 2)


class ToolCallAuthTests(unittest.TestCase):
    def test_tools_call_includes_actor_token_when_enabled(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings(
            enable_actor_token=True,
            actor_client_id="actor-client-id",
            actor_client_secret="actor-client-secret",
            actor_scopes=("mcp:invoke", "mcp:read"),
            incoming_scope_prefix_to_strip="agent1:",
        )
        auth = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("agent1:find:domain:read", "openid"),
            server_config=_server_config(),
            settings=settings,
            cache=ExchangedTokenCache(),
            actor_token_provider=_ActorTokenProvider(
                settings=settings,
                exchange_client=fake_exchange_client,
            ),
            exchange_client=fake_exchange_client,
        )
        request = httpx.Request(
            "POST",
            "https://example.com/mcp",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )

        list(auth.auth_flow(request))

        self.assertEqual(len(fake_exchange_client.actor_requests), 1)
        self.assertEqual(fake_exchange_client.actor_requests[0]["client_id"], "actor-client-id")
        self.assertEqual(
            fake_exchange_client.actor_requests[0]["scopes"],
            ("mcp:invoke", "mcp:read"),
        )
        self.assertEqual(len(fake_exchange_client.exchange_requests), 1)
        self.assertEqual(fake_exchange_client.exchange_requests[0]["actor_token"], "actor-token-1")
        self.assertEqual(
            fake_exchange_client.exchange_requests[0]["scopes"],
            ("find:domain:read",),
        )
        self.assertEqual(request.headers["Authorization"], "Bearer transaction-token-1")

    def test_non_tool_call_skips_actor_token_and_exchange(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings(
            enable_actor_token=True,
            actor_client_id="actor-client-id",
            actor_client_secret="actor-client-secret",
        )
        auth = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("find:domain:read",),
            server_config=_server_config(),
            settings=settings,
            cache=ExchangedTokenCache(),
            actor_token_provider=_ActorTokenProvider(
                settings=settings,
                exchange_client=fake_exchange_client,
            ),
            exchange_client=fake_exchange_client,
        )
        request = httpx.Request(
            "POST",
            "https://example.com/mcp",
            content=json.dumps({"method": "tools/list"}).encode("utf-8"),
        )

        list(auth.auth_flow(request))

        self.assertEqual(fake_exchange_client.actor_requests, [])
        self.assertEqual(fake_exchange_client.exchange_requests, [])
        self.assertNotIn("Authorization", request.headers)

    def test_actor_token_is_reused_across_multiple_tool_call_exchanges(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings(
            enable_actor_token=True,
            actor_client_id="actor-client-id",
            actor_client_secret="actor-client-secret",
        )
        cache = ExchangedTokenCache()
        provider = _ActorTokenProvider(
            settings=settings,
            exchange_client=fake_exchange_client,
        )
        auth_one = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("find:domain:read",),
            server_config=_server_config(audience="https://example.com/mcp/one"),
            settings=settings,
            cache=cache,
            actor_token_provider=provider,
            exchange_client=fake_exchange_client,
        )
        auth_two = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("find:domain:read",),
            server_config=_server_config(audience="https://example.com/mcp/two"),
            settings=settings,
            cache=cache,
            actor_token_provider=provider,
            exchange_client=fake_exchange_client,
        )
        request_one = httpx.Request(
            "POST",
            "https://example.com/mcp/one",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )
        request_two = httpx.Request(
            "POST",
            "https://example.com/mcp/two",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )

        list(auth_one.auth_flow(request_one))
        list(auth_two.auth_flow(request_two))

        self.assertEqual(len(fake_exchange_client.actor_requests), 1)
        self.assertEqual(len(fake_exchange_client.exchange_requests), 2)
        self.assertEqual(fake_exchange_client.exchange_requests[0]["actor_token"], "actor-token-1")
        self.assertEqual(fake_exchange_client.exchange_requests[1]["actor_token"], "actor-token-1")

    def test_transaction_token_is_reused_within_same_auth_flow(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings()
        auth = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("find:domain:read",),
            server_config=_server_config(),
            settings=settings,
            cache=ExchangedTokenCache(),
            actor_token_provider=_ActorTokenProvider(
                settings=settings,
                exchange_client=fake_exchange_client,
            ),
            exchange_client=fake_exchange_client,
        )
        request_one = httpx.Request(
            "POST",
            "https://example.com/mcp",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )
        request_two = httpx.Request(
            "POST",
            "https://example.com/mcp",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )

        list(auth.auth_flow(request_one))
        list(auth.auth_flow(request_two))

        self.assertEqual(len(fake_exchange_client.exchange_requests), 1)
        self.assertEqual(request_one.headers["Authorization"], "Bearer transaction-token-1")
        self.assertEqual(request_two.headers["Authorization"], "Bearer transaction-token-1")

    def test_subject_only_exchange_remains_unchanged_when_actor_support_is_disabled(self) -> None:
        fake_exchange_client = _FakeExchangeClient()
        settings = _base_settings()
        auth = _ToolCallAuth(
            subject_token="subject-token",
            subject_sub="user-123",
            subject_scopes=("find:domain:read",),
            server_config=_server_config(),
            settings=settings,
            cache=ExchangedTokenCache(),
            actor_token_provider=_ActorTokenProvider(
                settings=settings,
                exchange_client=fake_exchange_client,
            ),
            exchange_client=fake_exchange_client,
        )
        request = httpx.Request(
            "POST",
            "https://example.com/mcp",
            content=json.dumps({"method": "tools/call"}).encode("utf-8"),
        )

        list(auth.auth_flow(request))

        self.assertEqual(fake_exchange_client.actor_requests, [])
        self.assertEqual(len(fake_exchange_client.exchange_requests), 1)
        self.assertIsNone(fake_exchange_client.exchange_requests[0]["actor_token"])


if __name__ == "__main__":
    unittest.main()
