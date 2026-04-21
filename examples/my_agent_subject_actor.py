"""Bedrock AgentCore example that requires both subject and actor token exchange."""

from __future__ import annotations

from pathlib import Path

from agentcore_runtime import create_agentcore_app

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MCP_CONFIG_PATH = BASE_DIR / "mcp_servers.yaml"
DEFAULT_SYSTEM_PROMPT = (
    "You are an AI agent with access to downstream MCP servers. "
    "Use available tools to answer user queries. "
    "All tool calls are authenticated with PingFederate-issued transaction tokens "
    "produced from the caller subject token plus a global actor token minted by the SDK. "
    "If a tool call returns an insufficient_scope payload, return only that JSON payload with no explanation."
)
app = create_agentcore_app(
    default_mcp_config_path=DEFAULT_MCP_CONFIG_PATH,
    default_system_prompt=DEFAULT_SYSTEM_PROMPT,
    require_actor_token=True,
)


if __name__ == "__main__":
    app.run()
