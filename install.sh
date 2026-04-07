#!/bin/bash
# ClaudeSafeOps one-click installer
# Usage: ./install.sh
#
# Does three things:
# 1. Check dependencies (python3, jq)
# 2. Initialize user data directory ~/.claude-safe-ops/
# 3. Set script permissions
#
# Project code and user data are fully isolated:
#   Project repo -> code + default rules (git-managed)
#   ~/.claude-safe-ops/ -> host config, credentials, audit logs (user-private, not in git)

set -euo pipefail

GREEN='\033[92m'; YELLOW='\033[93m'; RED='\033[91m'; CYAN='\033[96m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { echo -e "${CYAN}[INFO]${RESET} $1"; }
ok()    { echo -e "${GREEN}[ OK ]${RESET} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $1"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_DIR="$HOME/.claude-safe-ops"

echo ""
echo -e "${BOLD}  ClaudeSafeOps Installer${RESET}"
echo -e "  Project (项目): ${CYAN}${PROJECT_DIR}${RESET}"
echo -e "  Data (数据): ${CYAN}${USER_DIR}/${RESET}"
echo ""

# ── 1. Dependency check ──────────────────────────────────────────
info "Checking dependencies... (检查依赖)"

command -v python3 &>/dev/null && ok "python3: $(python3 --version 2>&1)" || warn "python3 not found; risk assessment will use shell fallback (python3 未找到，风险评估将使用 shell 降级模式)"
command -v jq &>/dev/null && ok "jq: $(jq --version 2>&1)" || { warn "jq not installed, required by hooks (jq 未安装，hooks 需要)"; echo "  brew install jq (macOS) / apt install jq (Linux)"; }

# Install Python dependencies
if command -v python3 &>/dev/null; then
    python3 -m pip install -r "${PROJECT_DIR}/requirements.txt" --quiet 2>/dev/null && ok "Python dependencies installed (Python 依赖已安装)" || warn "pip install failed, please run manually: pip install -r requirements.txt (pip install 失败，请手动安装)"
fi

echo ""

# ── 2. Initialize ~/.claude-safe-ops/ ──────────────────────────────
info "Initializing user data directory... (初始化用户数据目录)"

mkdir -p "${USER_DIR}"/{config,audit,session,logs,playbooks,cache/hosts}

# Copy config templates (do not overwrite existing files)
if [[ ! -f "${USER_DIR}/config/hosts.yaml" ]]; then
    cp "${PROJECT_DIR}/src/config/hosts.example.yaml" "${USER_DIR}/config/hosts.yaml"
    ok "Host config template → ~/.claude-safe-ops/config/hosts.yaml (主机配置模板)"
    warn "← Edit this file to add your servers (请编辑此文件添加你的服务器)"
else
    ok "Host config exists, skipping (主机配置已存在，跳过)"
fi

if [[ ! -f "${USER_DIR}/config/credentials.yaml" ]]; then
    cp "${PROJECT_DIR}/src/config/credentials.example.yaml" "${USER_DIR}/config/credentials.yaml"
    chmod 600 "${USER_DIR}/config/credentials.yaml"
    ok "Credentials template → ~/.claude-safe-ops/config/credentials.yaml (perm: 600) (凭据模板)"
else
    ok "Credentials config exists, skipping (凭据配置已存在，跳过)"
fi

echo ""

# ── 3. SSH ControlMaster (connection reuse for Claude Code mode) ──
info "Configuring SSH connection reuse... (配置 SSH 连接复用)"

SSH_CONFIG="$HOME/.ssh/config"
SSH_SOCKETS="$HOME/.ssh/sockets"

# Create sockets directory
mkdir -p "${SSH_SOCKETS}"
chmod 700 "${SSH_SOCKETS}"

# Check if ControlMaster is already configured
if [[ -f "${SSH_CONFIG}" ]] && grep -q "ControlMaster" "${SSH_CONFIG}" 2>/dev/null; then
    ok "SSH ControlMaster already configured (SSH 连接复用已配置)"
else
    if [[ -f "${SSH_CONFIG}" ]]; then
        # Append to existing Host * block or add new one
        if grep -q "^Host \*" "${SSH_CONFIG}" 2>/dev/null; then
            warn "Found 'Host *' in ~/.ssh/config but no ControlMaster (发现 Host * 但未配置连接复用)"
            warn "Please add these lines under 'Host *' manually: (请手动在 Host * 下添加以下配置)"
            echo -e "    ${CYAN}ControlMaster auto${RESET}"
            echo -e "    ${CYAN}ControlPath ~/.ssh/sockets/%r@%h-%p${RESET}"
            echo -e "    ${CYAN}ControlPersist 600${RESET}"
        else
            # No Host * block, safe to append
            cat >> "${SSH_CONFIG}" <<'EOF'

# ClaudeSafeOps: SSH connection reuse for Claude Code mode
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
EOF
            ok "SSH ControlMaster added to ~/.ssh/config (SSH 连接复用已添加)"
        fi
    else
        # No ssh config at all, create one
        mkdir -p "$HOME/.ssh"
        chmod 700 "$HOME/.ssh"
        cat > "${SSH_CONFIG}" <<'EOF'
# ClaudeSafeOps: SSH connection reuse for Claude Code mode
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
    TCPKeepAlive yes
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
EOF
        chmod 600 "${SSH_CONFIG}"
        ok "Created ~/.ssh/config with ControlMaster (已创建 SSH 配置并启用连接复用)"
    fi
fi

echo ""

# ── 4. Script permissions ──────────────────────────────────────────
info "Setting script permissions... (设置脚本权限)"
chmod +x "${PROJECT_DIR}/scripts/"*.sh "${PROJECT_DIR}/scripts/"*.py 2>/dev/null || true
ok "All scripts in scripts/ are now executable (scripts/ 下所有脚本已设置可执行)"

echo ""

# ── Done ──────────────────────────────────────────────────
echo -e "${GREEN}${BOLD}Installation complete! (安装完成)${RESET}"
echo ""
echo "File layout:"
echo -e "  ${BOLD}Project code${RESET} (git-managed, shared)"
echo -e "    ${PROJECT_DIR}/"
echo ""
echo -e "  ${BOLD}User data${RESET} (private, not in git)"
echo -e "    ~/.claude-safe-ops/"
echo -e "    ├── config/hosts.yaml         ${CYAN}← Edit to add your servers (编辑添加服务器)${RESET}"
echo -e "    ├── config/credentials.yaml   ${CYAN}← SSH credentials (perm 600) (SSH 凭据配置)${RESET}"
echo -e "    ├── config/risk_rules.yaml    ${CYAN}← Custom risk rules, optional (自定义风险规则)${RESET}"
echo -e "    ├── playbooks/                ${CYAN}← User playbooks (用户运维剧本)${RESET}"
echo -e "    ├── audit/                    ${CYAN}← Audit logs, auto-written (审计日志)${RESET}"
echo -e "    └── session/                  ${CYAN}← Current session (当前连接会话)${RESET}"
echo ""
echo -e "  ${BOLD}SSH connection reuse${RESET}"
echo -e "    ~/.ssh/sockets/               ${CYAN}← ControlMaster sockets (连接复用 socket)${RESET}"
echo -e "    ~/.ssh/config                 ${CYAN}← ControlMaster + host aliases (连接配置)${RESET}"
echo ""
echo "Next steps:"
echo -e "  1. ${CYAN}vim ~/.claude-safe-ops/config/hosts.yaml${RESET}  Add servers (添加服务器)"
echo -e "  2. ${CYAN}ssh-copy-id user@your-server${RESET}        Set up key auth (配置免密登录)"
echo -e "  3. Add host aliases to ${CYAN}~/.ssh/config${RESET} matching hosts.yaml (添加 SSH 别名)"
echo -e "  4. ${CYAN}claude${RESET}                              Launch Claude Code in project dir"
echo -e "     Say: ${GREEN}\"Check my server disk space\"${RESET}"
echo ""
