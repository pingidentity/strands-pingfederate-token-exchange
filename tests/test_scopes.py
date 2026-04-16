from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aws_strands_pf_sdk.scopes import join_scopes, resolve_exchange_scopes


class ResolveExchangeScopesTests(unittest.TestCase):
    def test_forwards_matching_scopes_after_prefix_strip(self) -> None:
        scopes = resolve_exchange_scopes(
            ("agent1:find:domain:read", "agent1:find:domain:write", "openid"),
            scope_prefix="find:domain:",
            default_scopes=("find:domain",),
            prefix_to_strip="agent1:",
        )

        self.assertEqual(scopes, ("find:domain:read", "find:domain:write"))

    def test_falls_back_to_default_scopes(self) -> None:
        scopes = resolve_exchange_scopes(
            ("openid", "profile"),
            scope_prefix="find:domain:",
            default_scopes=("find:domain",),
        )

        self.assertEqual(scopes, ("find:domain",))

    def test_join_scopes_returns_none_for_empty_scopes(self) -> None:
        self.assertIsNone(join_scopes(()))


if __name__ == "__main__":
    unittest.main()
