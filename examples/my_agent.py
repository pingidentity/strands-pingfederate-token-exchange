"""Example FastAPI runtime for the SDK."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from strands import Agent

from aws_strands_pf_sdk.agentcore import (
    extract_subject_token,
    parse_scope_error_payload,
    serialize_agent_message,
)
from aws_strands_pf_sdk.config import PingFederateSettings, load_server_configs
from aws_strands_pf_sdk.errors import AuthenticationError, ConfigurationError, TokenExchangeError
from aws_strands_pf_sdk.mcp import create_mcp_clients

load_dotenv()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MCP_CONFIG_PATH = BASE_DIR / "mcp_servers.yaml"
DEFAULT_SYSTEM_PROMPT = (
    "You are an AI agent with access to downstream MCP servers. "
    "Use available tools to answer user queries. "
    "All tool calls are authenticated with PingFederate-issued delegated access tokens. "
    "If a tool call returns an insufficient_scope payload, return only that JSON payload with no explanation."
)

app = FastAPI(title="AWS Strands PingFederate Example Agent")


@lru_cache(maxsize=1)
def _load_runtime_config() -> tuple[PingFederateSettings, list[Any]]:
    settings = PingFederateSettings.from_env()
    config_path = Path(os.environ.get("MCP_SERVER_CONFIG", DEFAULT_MCP_CONFIG_PATH)).expanduser()
    server_configs = load_server_configs(config_path)
    return settings, server_configs


@app.get("/ping")
async def ping() -> dict[str, str]:
    """Required AgentCore health-check endpoint."""

    return {"status": "healthy"}


@app.post("/invocations")
async def invoke(request: Request) -> Any:
    """Handle an AgentCore invocation request."""

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    prompt = str(payload.get("prompt") or "Hello. How can I help?")

    try:
        subject_token = extract_subject_token(request.headers, payload)
        settings, server_configs = _load_runtime_config()
    except AuthenticationError as exc:
        return JSONResponse({"error": "invalid_request", "detail": str(exc)}, status_code=401)
    except ConfigurationError as exc:
        return JSONResponse({"error": "invalid_configuration", "detail": str(exc)}, status_code=500)

    try:
        mcp_clients = create_mcp_clients(
            subject_token=subject_token,
            server_configs=server_configs,
            settings=settings,
        )
        agent = Agent(
            tools=mcp_clients,
            system_prompt=os.environ.get("STRANDS_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        )
        result = agent(prompt)
    except TokenExchangeError as exc:
        return JSONResponse(
            {
                "error": exc.error,
                "detail": exc.description,
            },
            status_code=exc.status_code or 502,
        )
    except Exception as exc:
        LOGGER.exception("Agent invocation failed")
        return JSONResponse(
            {
                "error": "agent_invocation_failed",
                "detail": str(exc),
                "type": type(exc).__name__,
            },
            status_code=500,
        )

    message = getattr(result, "message", result)
    scope_error = parse_scope_error_payload(message)
    if scope_error is not None:
        return JSONResponse(scope_error, status_code=401)

    return serialize_agent_message(message)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("my_agent:app", host="0.0.0.0", port=8080, reload=False)
