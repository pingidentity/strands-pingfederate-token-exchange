from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aws_strands_pf_sdk.config import MCPServerConfig, PingFederateSettings
from aws_strands_pf_sdk.errors import ConfigurationError


class PingFederateSettingsTests(unittest.TestCase):
    def test_from_env_uses_canonical_names(self) -> None:
        settings = PingFederateSettings.from_env(
            {
                "PF_TOKEN_ENDPOINT": "https://issuer.example/as/token.oauth2",
                "PF_CLIENT_ID": "client-id",
                "PF_CLIENT_SECRET": "client-secret",
                "PF_VERIFY_SSL": "false",
                "PF_SCOPE_PREFIX_TO_STRIP": "agent1:",
            }
        )

        self.assertEqual(settings.token_endpoint, "https://issuer.example/as/token.oauth2")
        self.assertEqual(settings.client_id, "client-id")
        self.assertEqual(settings.client_secret, "client-secret")
        self.assertFalse(settings.verify_ssl)
        self.assertEqual(settings.incoming_scope_prefix_to_strip, "agent1:")

    def test_from_env_accepts_sdk_names(self) -> None:
        settings = PingFederateSettings.from_env(
            {
                "PF_TOKEN_ENDPOINT": "https://issuer.example/as/token.oauth2",
                "PF_CLIENT_ID": "client-id",
                "PF_CLIENT_SECRET": "client-secret",
                "PF_CLIENT_AUTH_METHOD": "client_secret_post",
                "PF_AUDIENCE_PARAMETER": "audience",
                "PF_REQUEST_TIMEOUT_SECONDS": "15",
            }
        )

        self.assertEqual(settings.client_auth_method, "client_secret_post")
        self.assertEqual(settings.audience_parameter, "audience")
        self.assertEqual(settings.request_timeout_seconds, 15.0)

    def test_from_env_loads_actor_settings_when_enabled(self) -> None:
        settings = PingFederateSettings.from_env(
            {
                "PF_TOKEN_ENDPOINT": "https://issuer.example/as/token.oauth2",
                "PF_CLIENT_ID": "client-id",
                "PF_CLIENT_SECRET": "client-secret",
                "PF_ENABLE_ACTOR_TOKEN": "true",
                "PF_ACTOR_CLIENT_ID": "actor-client-id",
                "PF_ACTOR_CLIENT_SECRET": "actor-client-secret",
                "PF_ACTOR_SCOPES": "mcp:invoke mcp:read",
            }
        )

        self.assertTrue(settings.enable_actor_token)
        self.assertEqual(settings.actor_client_id, "actor-client-id")
        self.assertEqual(settings.actor_client_secret, "actor-client-secret")
        self.assertEqual(settings.actor_scopes, ("mcp:invoke", "mcp:read"))

    def test_from_env_requires_actor_credentials_when_enabled(self) -> None:
        with self.assertRaises(ConfigurationError):
            PingFederateSettings.from_env(
                {
                    "PF_TOKEN_ENDPOINT": "https://issuer.example/as/token.oauth2",
                    "PF_CLIENT_ID": "client-id",
                    "PF_CLIENT_SECRET": "client-secret",
                    "PF_ENABLE_ACTOR_TOKEN": "true",
                    "PF_ACTOR_CLIENT_ID": "actor-client-id",
                }
            )

    def test_from_env_ignores_missing_actor_credentials_when_disabled(self) -> None:
        settings = PingFederateSettings.from_env(
            {
                "PF_TOKEN_ENDPOINT": "https://issuer.example/as/token.oauth2",
                "PF_CLIENT_ID": "client-id",
                "PF_CLIENT_SECRET": "client-secret",
                "PF_ENABLE_ACTOR_TOKEN": "false",
                "PF_ACTOR_CLIENT_ID": "actor-client-id",
            }
        )

        self.assertFalse(settings.enable_actor_token)
        self.assertEqual(settings.actor_client_id, "actor-client-id")
        self.assertIsNone(settings.actor_client_secret)


class MCPServerConfigTests(unittest.TestCase):
    def test_from_mapping_uses_canonical_scope_keys(self) -> None:
        server = MCPServerConfig.from_mapping(
            {
                "name": "search",
                "url": "https://example.com/mcp",
                "audience": "https://example.com/mcp",
                "scope_prefix": "search:",
                "default_scopes": "search:read",
            }
        )

        self.assertEqual(server.scope_prefix, "search:")
        self.assertEqual(server.default_scopes, ("search:read",))

    def test_from_mapping_supports_default_scope_lists(self) -> None:
        server = MCPServerConfig.from_mapping(
            {
                "name": "search",
                "url": "https://example.com/mcp",
                "default_scopes": ["search:read", "search:write"],
            }
        )

        self.assertEqual(server.default_scopes, ("search:read", "search:write"))


if __name__ == "__main__":
    unittest.main()
