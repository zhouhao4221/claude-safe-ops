#!/bin/bash
# PostToolUse Hook: Audit logging
# Records all remote operations to ~/.claude-safe-ops/audit/command_audit.jsonl

set -euo pipefail

AUDIT_DIR="$HOME/.claude-safe-ops/audit"
AUDIT_FILE="${AUDIT_DIR}/command_audit.jsonl"
MAX_SIZE=$((50 * 1024 * 1024))

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [ -z "$COMMAND" ]; then
    exit 0
fi

# Only log remote operations
if ! echo "$COMMAND" | grep -qiE 'ssh |scp |rsync |ansible |ansible-playbook '; then
    exit 0
fi

EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_result.exit_code // -1' 2>/dev/null)
TARGET_HOST=$(echo "$COMMAND" | grep -oE '[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+' | head -1 || echo "unknown")
OPERATOR=$(whoami 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "$AUDIT_DIR"

# Log rotation
if [ -f "$AUDIT_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$AUDIT_FILE" 2>/dev/null || stat -c%s "$AUDIT_FILE" 2>/dev/null || echo 0)
    if [ "$FILE_SIZE" -gt "$MAX_SIZE" ]; then
        mv "$AUDIT_FILE" "${AUDIT_FILE}.$(date +%Y%m%d_%H%M%S).bak"
    fi
fi

jq -nc \
    --arg ts "$TIMESTAMP" \
    --arg host "$TARGET_HOST" \
    --arg cmd "$COMMAND" \
    --arg exit_code "$EXIT_CODE" \
    --arg operator "$OPERATOR" \
    '{timestamp: $ts, host: $host, command: $cmd, exit_code: ($exit_code | tonumber), operator: $operator}' \
    >> "$AUDIT_FILE" 2>/dev/null || true

exit 0
