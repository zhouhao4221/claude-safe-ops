#!/bin/bash
# PreToolUse Hook: SSH remote command risk assessment
# Triggered automatically when Claude Code invokes the Bash tool
# Detect remote ops -> extract command -> assess risk -> allow/confirm/block

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RULES_FILE="${PROJECT_ROOT}/src/config/risk_rules.yaml"
USER_RULES="$HOME/.claude-safe-ops/config/risk_rules.yaml"

# Read stdin JSON
INPUT=$(cat)

# Extract command
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [ -z "$COMMAND" ]; then
    exit 0
fi

# ── Quick check: contains remote operation? ──
if ! echo "$COMMAND" | grep -qiE 'ssh |scp |rsync |ansible |ansible-playbook '; then
    exit 0
fi

# ── Extract the actual remote command ──
REMOTE_CMD=""

if echo "$COMMAND" | grep -qiE '^\s*ssh\s'; then
    REMOTE_CMD=$(echo "$COMMAND" | sed -E "
        s/^\s*ssh\s+//;
        s/(-[oipFJL]\s+\S+\s+)//g;
        s/(-[46AaCfGgKkMNnqsTtVvXxYy]\s*)//g;
        s/^[^ ]+\s+//;
        s/^['\"]//;
        s/['\"]$//;
    ")
elif echo "$COMMAND" | grep -qiE '^\s*scp\s'; then
    REMOTE_CMD="scp_file_transfer"
elif echo "$COMMAND" | grep -qiE 'ansible.*-a\s'; then
    REMOTE_CMD=$(echo "$COMMAND" | sed -E "s/.*-a\s+['\"]?([^'\"]+)['\"]?.*/\1/")
elif echo "$COMMAND" | grep -qiE '^\s*rsync\s'; then
    REMOTE_CMD="rsync_file_sync"
fi

if [ -z "$REMOTE_CMD" ]; then
    REMOTE_CMD="$COMMAND"
fi

# Extract target host
TARGET_HOST=$(echo "$COMMAND" | grep -oE '[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+' | head -1 || echo "unknown")

# ── Risk assessment (Python preferred, shell fallback) ──
RISK_RESULT=""

# Rule file priority: user custom > project default
EVAL_RULES="$RULES_FILE"
if [ -f "$USER_RULES" ]; then
    EVAL_RULES="$USER_RULES"
fi

if command -v python3 &>/dev/null && [ -f "$EVAL_RULES" ]; then
    RISK_RESULT=$(echo "$REMOTE_CMD" | python3 "${PROJECT_ROOT}/scripts/_risk_eval.py" "$EVAL_RULES" 2>/dev/null || echo "")
fi

# Shell fallback
if [ -z "$RISK_RESULT" ]; then
    RISK_LEVEL="MEDIUM"
    MATCH_DESC="Unknown command (fallback mode)"

    if echo "$REMOTE_CMD" | grep -qiE 'rm\s+(-\w*f\w*\s+)?/\s*$|DROP\s+DATABASE|TRUNCATE\s+TABLE|wipefs|format\s+/dev/'; then
        RISK_LEVEL="CRITICAL"; MATCH_DESC="Critical dangerous operation"
    elif echo "$REMOTE_CMD" | grep -qiE 'rm\s+-\w*rf|fdisk|mkfs|dd\s+|iptables\s+-F|kill\s+-9|shutdown|reboot|userdel|passwd'; then
        RISK_LEVEL="HIGH"; MATCH_DESC="High-risk operation"
    elif echo "$REMOTE_CMD" | grep -qiE '^\s*(ls|cat|df|free|uptime|ps|top|ss|ip\s+a|hostname|whoami|date|w|last|head|tail|grep|find|du|uname|id)(\s|$)'; then
        RISK_LEVEL="LOW"; MATCH_DESC="Read-only operation"
    fi

    RISK_RESULT="{\"risk_level\":\"${RISK_LEVEL}\",\"matched_rules\":[\"${MATCH_DESC}\"],\"default\":false}"
fi

# ── Parse result and decide ──
RISK_LEVEL=$(echo "$RISK_RESULT" | jq -r '.risk_level // "MEDIUM"')
MATCHED_RULES=$(echo "$RISK_RESULT" | jq -r '.matched_rules // [] | join(", ")')

case "$RISK_LEVEL" in
    LOW)
        exit 0
        ;;
    MEDIUM)
        jq -n --arg reason "⚠️ Medium-risk remote operation (中风险远程操作)
Target (目标): ${TARGET_HOST}
Remote command (远程命令): ${REMOTE_CMD}
Matched rules (匹配规则): ${MATCHED_RULES:-No rule matched, default MEDIUM (未匹配规则，默认MEDIUM)}" \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason } }'
        ;;
    HIGH)
        jq -n --arg reason "🚫 High-risk remote operation blocked! (高风险远程操作已拦截)
Risk level (风险等级): HIGH - manual execution required (强制手动执行)
Target (目标): ${TARGET_HOST}
Remote command (远程命令): ${REMOTE_CMD}
Matched rules (匹配规则): ${MATCHED_RULES}

Please execute this command manually on the target host. (请在目标主机终端手动执行此命令)" \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason } }'
        ;;
    CRITICAL)
        jq -n --arg reason "🔴 Critical-risk operation blocked! (严重风险操作已拦截)
Risk level (风险等级): CRITICAL - approval workflow required (需审批流程)
Target (目标): ${TARGET_HOST}
Remote command (远程命令): ${REMOTE_CMD}
Matched rules (匹配规则): ${MATCHED_RULES}

Please submit a change request and execute during maintenance window. (请通过变更工单审批后在维护窗口内手动执行)" \
        '{ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason } }'
        ;;
esac
