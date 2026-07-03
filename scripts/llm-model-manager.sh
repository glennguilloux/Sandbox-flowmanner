#!/usr/bin/env bash
#
# llm-model-manager.sh — Swap the active llama-server model.
#
# Usage:
#   llm-model-manager.sh list           List available models + active model
#   llm-model-manager.sh status         Show current model + service health
#   llm-model-manager.sh activate <id>  Activate model <id> (restarts llama-server)
#
# Reads model presets from /opt/flowmanner/config/llm-models.yaml
# Regenerates the systemd drop-in override for llama-server.service,
# then restarts the service.

set -euo pipefail

CONFIG_FILE="/opt/flowmanner/config/llm-models.yaml"
SERVICE_NAME="llama-server"
OVERRIDE_DIR="/etc/systemd/system/${SERVICE_NAME}.service.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/10-model-override.conf"
LLAMA_SERVER_BIN="/mnt/apps/llama.cpp-mtp/build/bin/llama-server"
STATE_FILE="/run/llm-model-manager/active-model"
HEALTH_URL="http://127.0.0.1:11434/health"
HEALTH_TIMEOUT=120

log()   { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }
info()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] INFO: $*"; }
error() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: $*" >&2; }
die() { error "$*"; exit 1; }

# ── Python helper (reads YAML, outputs JSON) ─────────────────────────────────
# All YAML parsing goes through this to avoid quoting hell.

py_query() {
    CONFIG_FILE="$CONFIG_FILE" STATE_FILE="$STATE_FILE" python3 "$@"
}

get_active_model() {
    if [[ -f "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "unknown"
    fi
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_list() {
    local active
    active=$(get_active_model)

    py_query -c "
import yaml, json, os

with open(os.environ['CONFIG_FILE']) as f:
    data = yaml.safe_load(f)

models = data.get('models', {})
active = '${active}'

result = {
    'active_model': active,
    'models': {}
}
for mid, m in models.items():
    result['models'][mid] = {
        'display_name': m.get('display_name', mid),
        'description': m.get('description', ''),
        'architecture': m.get('architecture', 'unknown'),
        'quantization': m.get('quantization', 'unknown'),
        'model_path': m.get('model_path', ''),
        'ctx_size': m.get('ctx_size', 32768),
        'spec_type': m.get('spec_type', 'none'),
        'is_active': mid == active,
    }

print(json.dumps(result, indent=2))
"
}

cmd_status() {
    local active
    active=$(get_active_model)
    local service_status
    service_status=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")

    local http_code health_status
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        health_status="healthy"
    elif [[ "$http_code" == "000" ]]; then
        health_status="unreachable"
    else
        health_status="http_${http_code}"
    fi

    local display_name
    display_name=$(py_query -c "
import yaml, os
with open(os.environ['CONFIG_FILE']) as f:
    data = yaml.safe_load(f)
m = data.get('models', {}).get('${active}', {})
print(m.get('display_name', '${active}'))
" 2>/dev/null || echo "$active")

    cat << EOF
{
  "active_model": "${active}",
  "display_name": "${display_name}",
  "service_status": "${service_status}",
  "health_status": "${health_status}",
  "health_url": "${HEALTH_URL}"
}
EOF
}

cmd_activate() {
    local model_id="$1"

    # Validate + extract model config as JSON
    local model_json
    model_json=$(py_query -c "
import yaml, json, os, sys
with open(os.environ['CONFIG_FILE']) as f:
    data = yaml.safe_load(f)
models = data.get('models', {})
mid = '${model_id}'
if mid not in models:
    sys.exit(1)
print(json.dumps(models[mid]))
" 2>/dev/null) || die "Model '${model_id}' not found in ${CONFIG_FILE}"

    [[ -n "$model_json" ]] || die "Model '${model_id}' not found in ${CONFIG_FILE}"

    local current
    current=$(get_active_model)
    if [[ "$current" == "$model_id" ]]; then
        info "Model '${model_id}' is already active."
        cmd_status
        exit 0
    fi

    info "Activating model '${model_id}'..."

    # Verify model file exists
    local model_path
    model_path=$(echo "$model_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_path',''))")
    [[ -f "$model_path" ]] || die "Model file not found: ${model_path}"

    # Build ExecStart from model config
    local exec_start
    exec_start=$(CONFIG_FILE="$CONFIG_FILE" MODEL_ID="$model_id" LLAMA_SERVER_BIN="$LLAMA_SERVER_BIN" python3 -c "
import yaml, json, os, shlex

with open(os.environ['CONFIG_FILE']) as f:
    data = yaml.safe_load(f)
m = data['models'][os.environ['MODEL_ID']]

parts = [
    os.environ['LLAMA_SERVER_BIN'],
    '--model', m['model_path'],
    '--host', '0.0.0.0',
    '--port', '11434',
    '--ctx-size', str(m.get('ctx_size', 32768)),
    '--gpu-layers', str(m.get('gpu_layers', 99)),
    '--flash-attn', 'on' if m.get('flash_attn', True) in (True, 'on', 'yes', 1) else 'off',
    '--parallel', str(m.get('parallel', 1)),
    '--cont-batching',
    '--log-file', '/var/log/llama-server.log',
]
spec_type = m.get('spec_type', 'none')
if spec_type and spec_type != 'none':
    parts += ['--spec-type', spec_type]
    if 'spec_draft_n_max' in m:
        parts += ['--spec-draft-n-max', str(m['spec_draft_n_max'])]
    # NOTE: --spec-p-min was removed in newer llama.cpp builds.
    # The build at /mnt/apps/llama.cpp-mtp (b45b455e) does not support it.
    # If you need p-min gating, use --override-kv or sampling params instead.
    if 'spec_ngram_simple_size_n' in m:
        parts += ['--spec-ngram-simple-size-n', str(m['spec_ngram_simple_size_n'])]
    if 'spec_ngram_simple_size_m' in m:
        parts += ['--spec-ngram-simple-size-m', str(m['spec_ngram_simple_size_m'])]
    if 'spec_ngram_simple_min_hits' in m:
        parts += ['--spec-ngram-simple-min-hits', str(m['spec_ngram_simple_min_hits'])]

print(' '.join(shlex.quote(p) for p in parts))
")
    [[ -n "$exec_start" ]] || die "Failed to build ExecStart for '${model_id}'"
    info "New ExecStart: ${exec_start}"

    # Write systemd drop-in override (needs root for /etc/systemd/)
    sudo mkdir -p "$OVERRIDE_DIR"
    sudo tee "$OVERRIDE_FILE" > /dev/null << EOF
# Auto-generated by llm-model-manager.sh — do not edit manually.
# To change the model, use: llm-model-manager.sh activate <model-id>
[Service]
ExecStart=
ExecStart=${exec_start}
EOF

    info "Wrote systemd override: ${OVERRIDE_FILE}"

    # Reload + restart (needs root)
    sudo systemctl daemon-reload
    info "Restarting ${SERVICE_NAME}..."
    sudo systemctl restart "$SERVICE_NAME"

    # Wait for health
    info "Waiting for ${SERVICE_NAME} to become healthy (timeout: ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$HEALTH_URL" 2>/dev/null || echo "000")
        if [[ "$http_code" == "200" ]]; then
            sudo mkdir -p "$(dirname "$STATE_FILE")"
            echo "$model_id" | sudo tee "$STATE_FILE" > /dev/null
            info "Model '${model_id}' activated and healthy (${elapsed}s)"
            cmd_status
            exit 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    error "Service did not become healthy within ${HEALTH_TIMEOUT}s"
    error "Check logs: journalctl -u ${SERVICE_NAME} --no-pager -n 50"
    exit 1
}

# ── Main ─────────────────────────────────────────────────────────────────────

[[ -f "$CONFIG_FILE" ]] || die "Config file not found: ${CONFIG_FILE}"

case "${1:-}" in
    list)     cmd_list ;;
    status)   cmd_status ;;
    activate)
        [[ -n "${2:-}" ]] || die "Usage: $0 activate <model-id>"
        cmd_activate "$2" ;;
    *)
        echo "Usage: $0 {list|status|activate <model-id>}"
        echo ""
        echo "Commands:"
        echo "  list           List available models and the active model"
        echo "  status         Show current model, service status, and health"
        echo "  activate <id>  Switch to model <id> (regenerates systemd + restarts)"
        echo ""
        echo "Config: ${CONFIG_FILE}"
        exit 1 ;;
esac
