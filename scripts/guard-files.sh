#!/bin/bash
# PreToolUse Hook: Protect sensitive files from Write/Edit/Read access
# Intercepts Write, Edit, Read, Glob tools to prevent:
#   - Tampering with hook config (.claude/)
#   - Reading credentials or SSH keys
#   - Modifying risk engine rules or hook scripts

set -euo pipefail

INPUT=$(cat)

# Extract tool name from hook event
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# Only guard file-access tools
case "$TOOL_NAME" in
    Write|Edit|Read|Glob) ;;
    *) exit 0 ;;
esac

# ── Extract file path from tool input ──
FILE_PATH=""
case "$TOOL_NAME" in
    Write|Read)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
        ;;
    Edit)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
        ;;
    Glob)
        # Glob uses pattern + path; check the search path
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null)
        PATTERN=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty' 2>/dev/null)
        ;;
esac

if [ -z "$FILE_PATH" ] && [ "$TOOL_NAME" != "Glob" ]; then
    exit 0
fi

# Resolve to absolute path for reliable matching
if [ -n "$FILE_PATH" ] && command -v realpath &>/dev/null; then
    ABS_PATH=$(realpath -m "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
else
    ABS_PATH="$FILE_PATH"
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_DATA="$HOME/.claude-safe-ops"

# ── Define protected zones ──

# CRITICAL: Always block Write/Edit (deny)
is_critical_write() {
    local path="$1"
    # Hook config — prevents disabling safety hooks
    [[ "$path" == *"/.claude/settings.json"* ]] && return 0
    [[ "$path" == *"/.claude/settings.local.json"* ]] && return 0
    # Hook scripts — prevents modifying safety logic
    [[ "$path" == "${PROJECT_ROOT}/scripts/risk-check.sh" ]] && return 0
    [[ "$path" == "${PROJECT_ROOT}/scripts/audit-log.sh" ]] && return 0
    [[ "$path" == "${PROJECT_ROOT}/scripts/guard-files.sh" ]] && return 0
    [[ "$path" == "${PROJECT_ROOT}/scripts/validate-hooks.sh" ]] && return 0
    return 1
}

# HIGH: Block Write/Edit, warn on Read (ask)
is_sensitive() {
    local path="$1"
    # Credentials
    [[ "$path" == *"/credentials.yaml"* ]] && return 0
    [[ "$path" == *"/credentials.yml"* ]] && return 0
    # SSH private keys
    [[ "$path" == "$HOME/.ssh/id_"* ]] && return 0
    [[ "$path" == "$HOME/.ssh/config" ]] && return 0
    # Risk engine core
    [[ "$path" == "${PROJECT_ROOT}/src/risk/engine.py" ]] && return 0
    # Env files
    [[ "$path" == *"/.env"* ]] && return 0
    return 1
}

# MEDIUM: Warn on Write/Edit (ask)
is_protected_config() {
    local path="$1"
    # User config files
    [[ "$path" == "${USER_DATA}/config/"* ]] && return 0
    # Project settings
    [[ "$path" == "${PROJECT_ROOT}/src/config/settings.py" ]] && return 0
    return 1
}

# ── Decision logic ──

if [ "$TOOL_NAME" = "Glob" ]; then
    # Glob: only warn if scanning SSH or credentials directories
    if [[ "$ABS_PATH" == "$HOME/.ssh"* ]] || [[ "$PATTERN" == *"credential"* ]] || [[ "$PATTERN" == *".ssh"* ]]; then
        jq -n --arg reason "🔍 File scan near sensitive area
Path: ${ABS_PATH:-cwd}
Pattern: ${PATTERN}
This may expose credentials or SSH keys." \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason } }'
    fi
    exit 0
fi

# Write/Edit operations
if [ "$TOOL_NAME" = "Write" ] || [ "$TOOL_NAME" = "Edit" ]; then
    if is_critical_write "$ABS_PATH"; then
        jq -n --arg reason "🔴 BLOCKED: Write to critical safety file
File: ${ABS_PATH}
Hook config and safety scripts cannot be modified.
This prevents disabling the security layer." \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason } }'
        exit 0
    fi

    if is_sensitive "$ABS_PATH"; then
        jq -n --arg reason "🚫 BLOCKED: Write to sensitive file
File: ${ABS_PATH}
Credentials, SSH keys, and risk engine cannot be modified via Claude.
Edit this file manually if needed." \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason } }'
        exit 0
    fi

    if is_protected_config "$ABS_PATH"; then
        jq -n --arg reason "⚠️ Writing to protected config file
File: ${ABS_PATH}
Please confirm this modification is intentional." \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason } }'
        exit 0
    fi
fi

# Read operations
if [ "$TOOL_NAME" = "Read" ]; then
    if is_sensitive "$ABS_PATH"; then
        jq -n --arg reason "⚠️ Reading sensitive file
File: ${ABS_PATH}
This file may contain credentials or private keys." \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason } }'
        exit 0
    fi
fi

# All other file operations — allow
exit 0
