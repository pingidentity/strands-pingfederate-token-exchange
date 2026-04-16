"""Configuration models and loaders for the SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigurationError

DEFAULT_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
DEFAULT_REQUESTED_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
SUPPORTED_CLIENT_AUTH_METHODS = {"client_secret_basic", "client_secret_post"}
SUPPORTED_AUDIENCE_PARAMETERS = {"resource", "audience"}


def _read_optional(env: Mapping[str, str], name: str, *, default: str | None = None) -> str | None:
    value = env.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _read_required(env: Mapping[str, str], name: str) -> str:
    value = _read_optional(env, name)
    if value is None:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_float(value: str | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"Expected a numeric timeout value, got: {value}") from exc


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _normalize_scopes(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(scope for scope in value.split() if scope)
    if isinstance(value, (list, tuple)):
        return tuple(str(scope).strip() for scope in value if str(scope).strip())
    raise ConfigurationError(f"Unsupported scope value: {value!r}")


@dataclass(frozen=True, slots=True)
class PingFederateSettings:
    """Settings for PingFederate RFC 8693 token exchange."""

    token_endpoint: str
    client_id: str
    client_secret: str
    subject_token_type: str = DEFAULT_SUBJECT_TOKEN_TYPE
    requested_token_type: str | None = DEFAULT_REQUESTED_TOKEN_TYPE
    verify_ssl: bool = True
    incoming_scope_prefix_to_strip: str | None = None
    client_auth_method: str = "client_secret_basic"
    audience_parameter: str = "resource"
    request_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PingFederateSettings":
        """Build settings from canonical `PF_*` environment variables."""

        values = os.environ if env is None else env
        token_endpoint = _read_required(values, "PF_TOKEN_ENDPOINT")
        client_id = _read_required(values, "PF_CLIENT_ID")
        client_secret = _read_required(values, "PF_CLIENT_SECRET")
        subject_token_type = _read_optional(
            values,
            "PF_SUBJECT_TOKEN_TYPE",
            default=DEFAULT_SUBJECT_TOKEN_TYPE,
        )
        requested_token_type = _read_optional(
            values,
            "PF_REQUESTED_TOKEN_TYPE",
            default=DEFAULT_REQUESTED_TOKEN_TYPE,
        )
        verify_ssl = _parse_bool(
            _read_optional(values, "PF_VERIFY_SSL"),
            default=True,
        )
        incoming_scope_prefix_to_strip = _read_optional(values, "PF_SCOPE_PREFIX_TO_STRIP")
        client_auth_method = _read_optional(
            values,
            "PF_CLIENT_AUTH_METHOD",
            default="client_secret_basic",
        )
        if client_auth_method not in SUPPORTED_CLIENT_AUTH_METHODS:
            supported = ", ".join(sorted(SUPPORTED_CLIENT_AUTH_METHODS))
            raise ConfigurationError(
                f"Unsupported client auth method '{client_auth_method}'. Supported values: {supported}"
            )

        audience_parameter = _read_optional(
            values,
            "PF_AUDIENCE_PARAMETER",
            default="resource",
        )
        if audience_parameter not in SUPPORTED_AUDIENCE_PARAMETERS:
            supported = ", ".join(sorted(SUPPORTED_AUDIENCE_PARAMETERS))
            raise ConfigurationError(
                f"Unsupported audience parameter '{audience_parameter}'. Supported values: {supported}"
            )

        request_timeout_seconds = _parse_float(
            _read_optional(values, "PF_REQUEST_TIMEOUT_SECONDS"),
            default=10.0,
        )
        return cls(
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            subject_token_type=subject_token_type,
            requested_token_type=requested_token_type,
            verify_ssl=verify_ssl,
            incoming_scope_prefix_to_strip=incoming_scope_prefix_to_strip,
            client_auth_method=client_auth_method,
            audience_parameter=audience_parameter,
            request_timeout_seconds=request_timeout_seconds,
        )


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """Config for a single downstream MCP server."""

    name: str
    url: str
    audience: str | None = None
    scope_prefix: str | None = None
    default_scopes: tuple[str, ...] = ()
    description: str | None = None
    transport: str = "streamable_http"
    verify_ssl: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MCPServerConfig":
        name = str(data.get("name", "")).strip()
        url = str(data.get("url", "")).strip()
        if not name:
            raise ConfigurationError("Each MCP server entry must include a non-empty 'name'")
        if not url:
            raise ConfigurationError(f"MCP server '{name}' is missing a non-empty 'url'")

        scope_prefix = data.get("scope_prefix")
        default_scopes = data.get("default_scopes")
        transport = str(data.get("transport", "streamable_http")).strip() or "streamable_http"
        description = data.get("description")
        audience = data.get("audience")
        verify_ssl = _coerce_bool(data.get("verify_ssl"), default=True)

        return cls(
            name=name,
            url=url,
            audience=str(audience).strip() if audience else None,
            scope_prefix=str(scope_prefix).strip() if scope_prefix else None,
            default_scopes=_normalize_scopes(default_scopes),
            description=str(description).strip() if description else None,
            transport=transport,
            verify_ssl=verify_ssl,
        )


def load_server_configs(path: str | Path) -> list[MCPServerConfig]:
    """Load MCP server definitions from a YAML file."""

    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ConfigurationError(
            "PyYAML is required to load MCP server configuration files"
        ) from exc

    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigurationError(f"MCP server config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    raw_servers = payload.get("servers")
    if raw_servers is None:
        raise ConfigurationError(f"MCP server config file {config_path} is missing the top-level 'servers' key")
    if not isinstance(raw_servers, list):
        raise ConfigurationError(f"The 'servers' entry in {config_path} must be a list")

    return [MCPServerConfig.from_mapping(item) for item in raw_servers]
