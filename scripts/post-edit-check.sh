#!/usr/bin/env bash
# Flowmanner Mission Gate — Post-Edit Validation
# Quick validation after each file edit.
# Usage: ./post-edit-check.sh <file-path>
# Returns: 0 (clean) or 1 (errors with output on stderr)

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || -z "${1:-}" ]]; then
    echo "Usage: post-edit-check.sh <file-path>"
    echo ""
    echo "Validates a single file after editing:"
    echo "  .ts/.tsx  → tsc --noEmit (frontend project)"
    echo "  .js/.jsx  → node --check"
    echo "  .py       → python -m py_compile"
    echo "  .sh       → bash -n"
    echo ""
    echo "Returns exit code 0 (clean) or 1 (errors)."
    echo "Errors are printed to stderr."
    exit 0
fi

FILE_PATH="${1:-}"

if [[ ! -f "$FILE_PATH" ]]; then
    echo "ERROR: File not found: $FILE_PATH" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_ROOT="/home/glenn/FlowmannerV2-frontend"
EXT="${FILE_PATH##*.}"

# ── Resolve path to determine context ──────────────────────────────────────────

in_frontend() {
    local file_real frontend_real
    file_real=$(realpath "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
    frontend_real=$(realpath "$FRONTEND_ROOT" 2>/dev/null || echo "$FRONTEND_ROOT")
    [[ "$file_real" == "$frontend_real"/* ]]
}

in_backend() {
    local file_real backend_real
    file_real=$(realpath "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
    backend_real=$(realpath "$PROJECT_ROOT/backend" 2>/dev/null || echo "$PROJECT_ROOT/backend")
    [[ "$file_real" == "$backend_real"/* ]]
}

# ── TypeScript / JSX checks ───────────────────────────────────────────────────

check_typescript() {
    local file="$1"

    # Quick local check via node --check for plain JS
    if [[ "$EXT" == "js" || "$EXT" == "jsx" ]]; then
        local node_out
        if node_out=$(node --check "$file" 2>&1); then
            echo "PASS: JS syntax OK"
            return 0
        else
            echo "FAIL: Node syntax check failed" >&2
            echo "$node_out" >&2
            return 1
        fi
    fi

    # For .ts/.tsx — run tsc from the frontend project
    if [[ "$EXT" == "ts" || "$EXT" == "tsx" ]]; then
        if ! in_frontend; then
            echo "WARN: TS file not in frontend project — skipping tsc check" >&2
            return 0
        fi
        if [[ ! -x "$FRONTEND_ROOT/node_modules/.bin/tsc" ]]; then
            echo "WARN: tsc not available — skipping check" >&2
            return 0
        fi

        local tsc_out tsc_rc
        # Use pushd/popd to avoid cd pollution and avoid subshell return bug
        pushd "$FRONTEND_ROOT" >/dev/null
        if tsc_out=$(npx tsc --noEmit --pretty false 2>&1); then
            popd >/dev/null
            echo "PASS: TypeScript check OK"
            return 0
        else
            tsc_rc=$?
            popd >/dev/null
            local err_count
            err_count=$(echo "$tsc_out" | grep -c "error TS" || echo "0")
            echo "FAIL: TypeScript — $err_count error(s)" >&2
            echo "$tsc_out" | tail -30 >&2
            return 1
        fi
    fi

    return 0
}

# ── Python checks ─────────────────────────────────────────────────────────────

check_python() {
    local file="$1"

    if [[ "$EXT" != "py" ]]; then
        return 0
    fi

    if in_backend && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^backend$'; then
        # Map host path to container path using parameter expansion
        local container_path="/app/${file#${PROJECT_ROOT}/backend/}"
        if docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T backend \
            python -m py_compile "$container_path" 2>&1; then
            echo "PASS: Python syntax OK (container)"
            return 0
        else
            echo "FAIL: Python syntax error (container)" >&2
            return 1
        fi
    else
        if python3 -m py_compile "$file" 2>&1; then
            echo "PASS: Python syntax OK"
            return 0
        else
            echo "FAIL: Python syntax error" >&2
            return 1
        fi
    fi
}

# ── Shell script checks ────────────────────────────────────────────────────────

check_shell() {
    local file="$1"
    if [[ "$EXT" != "sh" && "$EXT" != "bash" ]]; then
        return 0
    fi
    if command -v shellcheck &>/dev/null; then
        if shellcheck -S error "$file" 2>&1; then
            echo "PASS: ShellCheck OK"
            return 0
        else
            return 1
        fi
    else
        if bash -n "$file" 2>&1; then
            echo "PASS: Shell syntax OK"
            return 0
        else
            echo "FAIL: Shell syntax error" >&2
            return 1
        fi
    fi
}

# ── Dockerfile checks ─────────────────────────────────────────────────────────

check_dockerfile() {
    local basename
    basename=$(basename "$1")
    if [[ "$basename" != "Dockerfile" && "$basename" != Dockerfile* ]]; then
        return 0
    fi
    if docker &>/dev/null; then
        echo "INFO: Dockerfile detected — use 'docker build' for full validation"
    fi
    return 0
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo "Checking: $FILE_PATH (ext: .$EXT)" >&2

    local overall=0
    local result=""

    case "$EXT" in
        ts|tsx|js|jsx)
            if check_typescript "$FILE_PATH"; then
                result="PASS"
            else
                overall=1
                result="FAIL"
            fi
            ;;
        py)
            if check_python "$FILE_PATH"; then
                result="PASS"
            else
                overall=1
                result="FAIL"
            fi
            ;;
        sh|bash)
            if check_shell "$FILE_PATH"; then
                result="PASS"
            else
                overall=1
                result="FAIL"
            fi
            ;;
        *)
            local basename
            basename=$(basename "$FILE_PATH")
            if [[ "$basename" == "Dockerfile" || "$basename" == Dockerfile* ]]; then
                check_dockerfile "$FILE_PATH"
                result="INFO"
            else
                result="SKIP (no check for .$EXT)"
            fi
            ;;
    esac

    echo "post_edit_check=$result" >&2
    exit $overall
}

main
