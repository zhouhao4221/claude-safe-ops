#!/usr/bin/env bash
# sensitive-input-guard.sh — UserPromptSubmit hook
# Blocks user prompts that contain passwords, tokens, keys, or other secrets
# before they are sent to the AI API.
#
# Runs on: UserPromptSubmit (before message leaves the client)
# Exit 2 = block submission with reason

set -euo pipefail

# Read user prompt from hook input (stdin JSON)
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('prompt', ''))
" 2>/dev/null || echo "$INPUT")

# Skip empty or very short prompts
if [ ${#PROMPT} -lt 6 ]; then
    exit 0
fi

# ============================================================
# Pattern definitions (POSIX ERE compatible for macOS grep -E)
# ============================================================

EXPLICIT_PATTERNS=(
    # Chinese patterns
    '密码[是为：:][[:space:]]*[^[:space:]]+'
    '口令[是为：:][[:space:]]*[^[:space:]]+'
    '令牌[是为：:][[:space:]]*[^[:space:]]+'
    '密钥[是为：:][[:space:]]*[^[:space:]]+'
    '秘钥[是为：:][[:space:]]*[^[:space:]]+'
    # English patterns
    'password[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'passwd[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'token[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'secret[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'api.?key[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'access.?key[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'private.?key[[:space:]]*(is|=|:)[[:space:]]*[^[:space:]]+'
    'credentials?[[:space:]]*(is|are|=|:)[[:space:]]*[^[:space:]]+'
)

STRUCTURAL_PATTERNS=(
    # AWS keys
    'AKIA[0-9A-Z]{16}'
    # GitHub tokens
    'gh[ps]_[A-Za-z0-9_]{36,}'
    'github_pat_[A-Za-z0-9_]{22,}'
    # GitLab tokens
    'glpat-[A-Za-z0-9-]{20,}'
    # Slack tokens
    'xox[bpors]-[A-Za-z0-9-]+'
    # Generic long secrets with credential keywords
    '(password|token|secret|key|credential)[[:space:]]*[=:][[:space:]]*[A-Za-z0-9+/=_-]{40,}'
    # SSH private key content
    '-----BEGIN[[:space:]]+(RSA|DSA|EC|OPENSSH)[[:space:]]+PRIVATE[[:space:]]+KEY-----'
    # Bearer tokens
    'Bearer[[:space:]]+[A-Za-z0-9_.~+/-]+='
)

# ============================================================
# Detection
# ============================================================

check_patterns() {
    local pattern_type="$1"
    shift
    local patterns=("$@")

    for pattern in "${patterns[@]}"; do
        if echo "$PROMPT" | grep -iE "$pattern" > /dev/null 2>&1; then
            echo "$pattern_type"
            return 0
        fi
    done
    return 1
}

# Check explicit patterns first (highest confidence)
if check_patterns "EXPLICIT" "${EXPLICIT_PATTERNS[@]}" > /dev/null; then
    # Exit code 2 = block with reason message
    echo '{"reason": "🔴 检测到敏感信息！/ Sensitive data detected!\n\n你的消息中似乎包含密码、Token 或密钥。为防止泄露，此消息已被拦截。\nYour message appears to contain a password, token, or key. It has been blocked to prevent leakage.\n\n安全替代方式 / Safe alternatives:\n  1. 写入配置文件: ~/.claude-safe-ops/config/credentials.yaml\n  2. 使用 SSH 密钥认证\n  3. 使用 SSH Agent\n  4. 通过 getpass() 交互输入（不会发送给 AI）"}' >&2
    exit 2
fi

# Check structural patterns (token formats)
if check_patterns "STRUCTURAL" "${STRUCTURAL_PATTERNS[@]}" > /dev/null; then
    echo '{"reason": "🔴 检测到密钥/Token 格式！/ Secret/Token pattern detected!\n\n你的消息中包含疑似 API Key、Token 或私钥内容。为防止泄露，此消息已被拦截。\nYour message contains what appears to be an API key, token, or private key. Blocked to prevent leakage.\n\n安全替代方式 / Safe alternatives:\n  1. 写入配置文件: ~/.claude-safe-ops/config/credentials.yaml\n  2. 设置环境变量（不要用 echo 打印）\n  3. 使用 SSH Agent 管理密钥"}' >&2
    exit 2
fi

# All clear
exit 0
