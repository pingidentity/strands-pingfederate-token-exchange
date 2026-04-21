"""Shared Bedrock AgentCore runtime builder for example applications."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp, RequestContext
from dotenv import load_dotenv
from strands import Agent

from aws_strands_pf_sdk.agentcore import (
    extract_subject_token,
    parse_scope_error_payload,
    serialize_agent_message,
)
from aws_strands_pf_sdk.config import MCPServerConfig, PingFederateSettings, load_server_configs
from aws_strands_pf_sdk.errors import AuthenticationError, ConfigurationError, TokenExchangeError
from aws_strands_pf_sdk.mcp import create_mcp_clients

load_dotenv()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
LOGGER = logging.getLogger(__name__)


def create_agentcore_app(
    *,
    default_mcp_config_path: Path,
    default_system_prompt: str,
    require_actor_token: bool = False,
) -> BedrockAgentCoreApp:
    """Build a Bedrock AgentCore example app around the SDK runtime helpers."""

    app = BedrockAgentCoreApp()

    @lru_cache(maxsize=1)
    def _load_runtime_config() -> tuple[PingFederateSettings, list[MCPServerConfig]]:
        settings = PingFederateSettings.from_env()
        if require_actor_token and not settings.enable_actor_token:
            raise ConfigurationError(
                "This example requires PF_ENABLE_ACTOR_TOKEN=true plus the PF_ACTOR_* settings."
            )

        config_path = Path(
            os.environ.get("MCP_SERVER_CONFIG", str(default_mcp_config_path))
        ).expanduser()
        server_configs = load_server_configs(config_path)
        return settings, server_configs

    @app.entrypoint
    def invoke(payload: dict[str, Any], context: RequestContext) -> Any:
        """Handle an AgentCore invocation request."""

        prompt = str(payload.get("prompt") or "Hello. How can I help?")
        request_headers = context.request_headers or {}

        try:
            subject_token = extract_subject_token(request_headers, payload)
            settings, server_configs = _load_runtime_config()
        except AuthenticationError as exc:
            return {"error": "invalid_request", "detail": str(exc)}
        except ConfigurationError as exc:
            return {"error": "invalid_configuration", "detail": str(exc)}

        try:
            mcp_clients = create_mcp_clients(
                subject_token=subject_token,
                server_configs=server_configs,
                settings=settings,
            )
            agent = Agent(
                tools=mcp_clients,
                system_prompt=os.environ.get("STRANDS_SYSTEM_PROMPT", default_system_prompt),
            )
            result = agent(prompt)
        except TokenExchangeError as exc:
            return {
                "error": exc.error,
                "detail": exc.description,
            }
        except Exception as exc:
            LOGGER.exception("Agent invocation failed")
            return {
                "error": "agent_invocation_failed",
                "detail": str(exc),
                "type": type(exc).__name__,
            }

        message = getattr(result, "message", result)
        scope_error = parse_scope_error_payload(message)
        if scope_error is not None:
            return scope_error

        return serialize_agent_message(message)

    return app
