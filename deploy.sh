#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
ENV_FILE=".env"
ENTRYPOINT="${AGENT_ENTRYPOINT:-examples/my_agent.py}"
REGION="${AWS_REGION:-us-west-2}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        fail "python3 not found. Install Python 3.10+."
    fi

    python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
PY
}

setup_venv() {
    check_python

    if [[ ! -d "$VENV_DIR" ]]; then
        info "Creating virtual environment"
        python3 -m venv "$VENV_DIR"
    fi

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    info "Installing SDK and example dependencies"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
}

install_agentcore_tooling() {
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    info "Installing AgentCore starter toolkit"
    pip install --quiet bedrock-agentcore-starter-toolkit
}

ensure_env_file() {
    if [[ -f "$ENV_FILE" ]]; then
        return
    fi

    if [[ -f ".env.example" ]]; then
        cp .env.example "$ENV_FILE"
        fail "Created .env from .env.example. Fill in the PingFederate values and rerun."
    fi

    fail "Missing .env and .env.example"
}

require_var() {
    local var_name="$1"
    if [[ -n "${!var_name:-}" ]]; then
        success "Found $var_name"
        return
    fi
    fail "Set $var_name in .env"
}

is_truthy() {
    local value="${1:-}"
    case "${value,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

validate_env() {
    ensure_env_file

    set -a
    # shellcheck disable=SC1091
    source "$ENV_FILE"
    set +a

    require_var PF_TOKEN_ENDPOINT
    require_var PF_CLIENT_ID
    require_var PF_CLIENT_SECRET
    if is_truthy "${PF_ENABLE_ACTOR_TOKEN:-false}"; then
        require_var PF_ACTOR_CLIENT_ID
        require_var PF_ACTOR_CLIENT_SECRET
    fi

    local mcp_config="${MCP_SERVER_CONFIG:-examples/mcp_servers.yaml}"
    if [[ ! -f "$mcp_config" ]]; then
        fail "MCP server config file not found: $mcp_config"
    fi
    if [[ ! -f "$ENTRYPOINT" ]]; then
        fail "Agent entrypoint not found: $ENTRYPOINT"
    fi

    success "Environment configuration looks valid"
}

check_aws() {
    if ! command -v aws >/dev/null 2>&1; then
        fail "AWS CLI not found. Install it before deploying."
    fi
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        fail "AWS credentials not configured. Run 'aws configure'."
    fi
}

run_local() {
    setup_venv
    validate_env

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    info "Starting AgentCore example runtime from $ENTRYPOINT on http://localhost:8080"
    info "Use Ctrl+C to stop it"
    PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" python "$ENTRYPOINT"
}

deploy_agent() {
    setup_venv
    validate_env
    check_aws
    install_agentcore_tooling

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    info "Configuring AgentCore runtime"
    agentcore configure \
        -e "$ENTRYPOINT" \
        -r "$REGION" \
        --disable-memory \
        --request-header-allowlist "Authorization"
    info "Deploying runtime"
    agentcore deploy
}

status_agent() {
    setup_venv
    install_agentcore_tooling

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    agentcore status
}

test_agent() {
    setup_venv
    install_agentcore_tooling

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    agentcore invoke '{
      "prompt": "What tools do you have available?",
      "authorization": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJzY29wZSI6Im9wZW5pZCIsImlhdCI6MTcwMDAwMDAwMH0."
    }'
}

destroy_agent() {
    setup_venv
    install_agentcore_tooling

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    warn "This removes the configured AgentCore runtime."
    read -rp "Continue? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        agentcore destroy
    fi
}

COMMAND="${1:-local}"

case "$COMMAND" in
    setup)
        setup_venv
        ;;
    validate)
        setup_venv
        validate_env
        ;;
    local)
        run_local
        ;;
    deploy)
        deploy_agent
        ;;
    test)
        test_agent
        ;;
    status)
        status_agent
        ;;
    destroy)
        destroy_agent
        ;;
    *)
        echo "Usage: $0 [setup|validate|local|deploy|test|status|destroy]"
        exit 1
        ;;
esac
