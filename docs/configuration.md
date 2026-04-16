# Configuration

## Environment Variables

The SDK uses the canonical `PF_*` variable names only.

Required:

- `PF_TOKEN_ENDPOINT`: PingFederate token endpoint used for RFC 8693 exchange.
- `PF_CLIENT_ID`: OAuth client identifier.
- `PF_CLIENT_SECRET`: OAuth client secret.

Optional:

- `PF_SUBJECT_TOKEN_TYPE`: Defaults to `urn:ietf:params:oauth:token-type:access_token`.
- `PF_REQUESTED_TOKEN_TYPE`: Defaults to `urn:ietf:params:oauth:token-type:access_token`.
- `PF_CLIENT_AUTH_METHOD`: `client_secret_basic` or `client_secret_post`. Default is `client_secret_basic`.
- `PF_AUDIENCE_PARAMETER`: `resource` or `audience`. Default is `resource`, which is the common PingFederate setup.
- `PF_VERIFY_SSL`: Defaults to `true`.
- `PF_SCOPE_PREFIX_TO_STRIP`: Optional prefix removed from incoming subject-token scopes before matching.
- `PF_REQUEST_TIMEOUT_SECONDS`: Defaults to `10`.
- `MCP_SERVER_CONFIG`: Optional path to the YAML file consumed by the example runtime. Defaults to `examples/mcp_servers.yaml`.
- `STRANDS_SYSTEM_PROMPT`: Optional override for the example runtime system prompt.

## MCP Server YAML

The SDK does not hardcode MCP server definitions. The example runtime reads a
YAML file with this shape:

```yaml
servers:
  - name: findadomain-dev
    description: Find available domains
    url: https://api.findadomain.dev/mcp
    transport: streamable_http
    audience: https://api.findadomain.dev/mcp
    scope_prefix: find:domain:
    default_scopes:
      - find:domain
    verify_ssl: true
```

Field notes:

- `name`: Required logical name used in logs.
- `url`: Required streamable HTTP MCP endpoint.
- `transport`: Only `streamable_http` is supported.
- `audience`: Optional. If omitted, the server URL is used as the audience/resource.
- `scope_prefix`: Optional. Matching inbound scopes are forwarded to token exchange.
- `default_scopes`: Optional fallback scopes if no inbound scopes match.
- `verify_ssl`: Optional, defaults to `true`.

## Scope Resolution

The scope-resolution behavior is intentionally simple:

1. Read scopes from the inbound subject token.
2. Optionally remove a shared prefix such as `agent1:`.
3. Forward the subset of scopes that start with the configured `scope_prefix`.
4. If no scopes match, request `default_scopes` instead.

This keeps the SDK deterministic and avoids embedding environment-specific
registration or consent behavior into the runtime.
