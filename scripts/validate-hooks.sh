#!/bin/bash
# PreToolUse Hook: Validate safety hooks integrity on first Bash invocation
# Checks that all required hooks are registered in .claude/settings.json
# Runs once per session (creates a stamp file to avoid repeated checks)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETTINGS_FILE="${PROJECT_ROOT}/.claude/settings.json"
STAMP_FILE="/tmp/.csops-hooks-validated-$$"

# Only validate once per session
if [ -f "$STAMP_FILE" ]; then
    exit 0
fi
touch "$STAMP_FILE"

# Read stdin (required by hook protocol) but we don't use it
cat > /dev/null

ISSUES=""

# ── Check settings.json exists ──
if [ ! -f "$SETTINGS_FILE" ]; then
    ISSUES="${ISSUES}• settings.json is missing\n"
fi

# ── Check required hook scripts exist and are executable ──
REQUIRED_SCRIPTS=(
    "scripts/risk-check.sh"
    "scripts/audit-log.sh"
    "scripts/guard-files.sh"
    "scripts/validate-hooks.sh"
)
for script in "${REQUIRED_SCRIPTS[@]}"; do
    FULL_PATH="${PROJECT_ROOT}/${script}"
    if [ ! -f "$FULL_PATH" ]; then
        ISSUES="${ISSUES}• Missing: ${script}\n"
    elif [ ! -x "$FULL_PATH" ]; then
        ISSUES="${ISSUES}• Not executable: ${script}\n"
    fi
done

# ── Check required hooks are registered in settings.json ──
if [ -f "$SETTINGS_FILE" ]; then
    REQUIRED_HOOKS=(
        "risk-check.sh"
        "audit-log.sh"
        "guard-files.sh"
    )
    for hook in "${REQUIRED_HOOKS[@]}"; do
        if ! grep -q "$hook" "$SETTINGS_FILE" 2>/dev/null; then
            ISSUES="${ISSUES}• Hook not registered: ${hook}\n"
        fi
    done
fi

# ── Check credentials file permissions ──
CRED_FILE="$HOME/.claude-safe-ops/config/credentials.yaml"
if [ -f "$CRED_FILE" ]; then
    PERMS=$(stat -f '%A' "$CRED_FILE" 2>/dev/null || stat -c '%a' "$CRED_FILE" 2>/dev/null || echo "")
    if [ -n "$PERMS" ] && [ "$PERMS" != "600" ]; then
        ISSUES="${ISSUES}• credentials.yaml has insecure permissions: ${PERMS} (should be 600)\n"
    fi
fi

# ── Report issues ──
if [ -n "$ISSUES" ]; then
    # Use printf to handle \n in ISSUES
    REASON=$(printf "🛡️ Safety hooks integrity check\n\nIssues found:\n${ISSUES}\nRun ./install.sh to repair, or fix manually.")
    jq -n --arg reason "$REASON" \
    '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason } }'
    exit 0
fi

# All checks passed — silent
exit 0
