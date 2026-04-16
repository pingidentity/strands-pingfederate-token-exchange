from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib import parse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aws_strands_pf_sdk.config import PingFederateSettings
from aws_strands_pf_sdk.errors import TokenExchangeError
from aws_strands_pf_sdk.token_exchange import PingFederateTokenExchangeClient


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class TokenExchangeClientTests(unittest.TestCase):
    def test_exchange_token_uses_basic_auth_and_resource_parameter(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, *, timeout, context):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["data"] = parse.parse_qs(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "access_token": "exchanged-token",
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "scope": "find:domain:read",
                }
            )

        settings = PingFederateSettings(
            token_endpoint="https://issuer.example/as/token.oauth2",
            client_id="client-id",
            client_secret="client-secret",
        )
        client = PingFederateTokenExchangeClient(settings, urlopen=fake_urlopen)
        result = client.exchange_token(
            "subject-token",
            audience="https://api.example.com/mcp",
            scopes=("find:domain:read",),
        )

        self.assertEqual(result.access_token, "exchanged-token")
        self.assertEqual(captured["url"], "https://issuer.example/as/token.oauth2")
        self.assertIn("Authorization", captured["headers"])
        self.assertEqual(captured["data"]["resource"], ["https://api.example.com/mcp"])
        self.assertEqual(captured["data"]["scope"], ["find:domain:read"])

    def test_exchange_token_raises_on_invalid_json(self) -> None:
        def fake_urlopen(request, *, timeout, context):
            del request, timeout, context
            return _FakeResponse({"unexpected": "value"})

        settings = PingFederateSettings(
            token_endpoint="https://issuer.example/as/token.oauth2",
            client_id="client-id",
            client_secret="client-secret",
        )
        client = PingFederateTokenExchangeClient(settings, urlopen=fake_urlopen)

        with self.assertRaises(TokenExchangeError):
            client.exchange_token("subject-token")


if __name__ == "__main__":
    unittest.main()
