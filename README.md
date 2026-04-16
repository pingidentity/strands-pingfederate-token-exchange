# AWS Strands PingFederate SDK

A Python SDK for using PingFederate RFC 8693 token exchange with AWS Strands
MCP tool calls.

The token exchange model in this SDK is:

- `subject token`: the inbound bearer token presented by the caller to the
  agent runtime
- `actor token`: an optional token included in the exchange request when the
  deployment needs explicit delegation context
- `transaction token`: the exchanged downstream access token returned by
  PingFederate and then attached to MCP `tools/call` requests

In other words, the SDK receives a caller's subject token, can optionally add
an actor token to the RFC 8693 exchange request, and uses the returned
transaction token for the actual downstream transaction against the MCP server.

The project is now split into:

- `src/aws_strands_pf_sdk/`: reusable SDK code
- `examples/`: a native Bedrock AgentCore runtime example and MCP config
- `tests/`: lightweight unit tests for the core logic
- `docs/`: configuration and scope notes

## Scope

This SDK focuses on the core token-exchange path:

- load PingFederate settings from environment variables
- load MCP server definitions from YAML
- exchange the inbound bearer token only when `tools/call` is executed
- cache exchanged tokens per invocation
- provide a native Bedrock AgentCore runtime example

Prerequisites:

- a PingFederate OAuth client is already registered for token exchange
- any required JWK generation, rotation, or key management is handled outside this SDK
- client authentication uses a supported shared-secret method
- downstream MCP servers are exposed over HTTP using `streamable_http`
- the AgentCore runtime forwards the inbound `Authorization` header to agent code

Additional design boundaries are documented explicitly instead of being
half-wired into the runtime.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[example]
```

## Quick Start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Fill in your PingFederate token endpoint and client credentials in `.env`.

3. Adjust the downstream MCP server definitions in `examples/mcp_servers.yaml`.

4. Run the example locally:

   ```bash
   ./deploy.sh local
   ```

5. Invoke the runtime:

   ```bash
   curl -s http://localhost:8080/invocations \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer <subject-token>' \
     -d '{"prompt":"What tools do you have?"}'
   ```

## Public SDK Surface

The reusable API is intentionally small:

```python
from aws_strands_pf_sdk.config import PingFederateSettings, load_server_configs
from aws_strands_pf_sdk.mcp import create_mcp_clients

settings = PingFederateSettings.from_env()
server_configs = load_server_configs("examples/mcp_servers.yaml")
clients = create_mcp_clients(
    subject_token=inbound_token,
    server_configs=server_configs,
    settings=settings,
)
```

`create_mcp_clients(...)` returns Strands `MCPClient` instances that:

- avoid token exchange for connection setup and tool discovery
- perform token exchange only for `tools/call`
- derive requested scopes from the subject token when possible
- fall back to configured default scopes when necessary

## Configuration

- Environment variables: [docs/configuration.md](docs/configuration.md)
- Design boundaries: [docs/design-boundaries.md](docs/design-boundaries.md)

Configuration uses the canonical `PF_*` environment variable names only.

## Example Layout

```text
examples/
  my_agent.py
  mcp_servers.yaml
src/
  aws_strands_pf_sdk/
tests/
docs/
```

## Development

Run the lightweight test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run a syntax-only check:

```bash
python3 -m compileall src examples tests
```
