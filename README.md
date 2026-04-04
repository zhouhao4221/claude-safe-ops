# ClaudeSafeOps

**AI-powered server operations with built-in risk control.**

Use natural language to manage servers — while a multi-layered safety engine ensures dangerous commands never execute without your explicit approval.

[中文文档](README.zh.md)

---

## Why ClaudeSafeOps

Traditional server ops: write commands manually, hope you don't typo `rm -rf /`.

ClaudeSafeOps: tell the AI what you want, and a **115-rule risk engine** + **4 security hooks** + **audit trail** ensure nothing catastrophic happens — even if the AI makes a mistake.

```
You say:  "clean up old logs on web-01"
AI does:  ssh web-01 'find /var/log -name "*.gz" -mtime +30 -delete'
Engine:   ⚠️ MEDIUM — file deletion, confirm? [y/N]
```

```
You say:  "drop the test database"
AI does:  ssh db-01 'DROP DATABASE test'
Engine:   🔴 CRITICAL — blocked. Requires approval workflow.
```

## Two Core Pillars

### 1. AI Automation

| Feature | Description |
|---------|-------------|
| **Natural language ops** | Tell Claude what to do; it constructs SSH commands automatically |
| **9 ops modules** | system, network, disk, process, deploy, backup, security, log, playbook |
| **Playbook system** | Save and reuse verified operation workflows with `{{variable}}` parameterization |
| **Auto language** | Claude detects your language and responds accordingly (en/zh/ko) |
| **Slash commands** | `/onboard`, `/health`, `/audit`, `/risk`, `/playbook`, `/lang` |

### 2. Risk Control

| Layer | Mechanism | What It Stops |
|-------|-----------|---------------|
| **Rule engine** | 115 regex rules (CRITICAL/HIGH/MEDIUM/LOW) | `rm -rf /`, `DROP DATABASE`, `shutdown`, `kill -9` |
| **Hook: risk-check** | PreToolUse on Bash | SSH/scp/rsync/ansible commands assessed before execution |
| **Hook: guard-files** | PreToolUse on Write/Edit/Read/Glob | Tampering with hook config, reading credentials/SSH keys |
| **Hook: validate-hooks** | PreToolUse on Bash (first call) | Detects if safety hooks have been removed or misconfigured |
| **Hook: audit-log** | PostToolUse on Bash | Every remote operation recorded to JSONL audit trail |
| **Credential isolation** | File permissions + getpass | Passwords never in logs, CLI args, or code |
| **File isolation** | `~/.claude-safe-ops/` separation | `git pull` never overwrites your config or credentials |

## Quick Start

```bash
git clone https://github.com/zhouhao4221/claude-safe-ops.git && cd claude-safe-ops
./install.sh
vim ~/.claude-safe-ops/config/hosts.yaml   # Add your servers
claude                                      # Launch Claude Code
```

Then just say:

> "Check disk space on web-01"
>
> "Restart nginx if the config is valid"
>
> "Any SSH brute-force attempts recently?"

## Security Architecture

### Defense in Depth

```
User (natural language)
  │
  ▼
Claude Code (AI constructs commands)
  │
  ├── /risk ──────────► Pre-check risk before executing
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Hook Layer (.claude/settings.json)                     │
│                                                         │
│  1. validate-hooks.sh  — verify safety integrity        │
│  2. risk-check.sh      — assess remote command risk     │
│  3. guard-files.sh     — protect sensitive files        │
│  4. audit-log.sh       — record all operations          │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Risk Engine (src/risk/engine.py)                       │
│                                                         │
│  115 built-in rules + custom YAML rules                 │
│  Priority: user custom > project YAML > built-in Python │
│  Default: unmatched commands → MEDIUM (confirm)         │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Execution Decision                                     │
│                                                         │
│  LOW      → auto-execute                                │
│  MEDIUM   → prompt for confirmation                     │
│  HIGH     → BLOCK, print manual command                 │
│  CRITICAL → BLOCK, require approval workflow            │
└─────────────────────────────────────────────────────────┘
  │
  ▼
SSH → Remote Server
  │
  ▼
Audit Log (~/.claude-safe-ops/audit/command_audit.jsonl)
```

### Risk Levels

| Level | Action | Examples |
|-------|--------|----------|
| **LOW** | Auto-allow | `df -h`, `ps aux`, `uptime`, `docker ps` |
| **MEDIUM** | Prompt for confirmation | `systemctl restart`, `chmod`, `kubectl apply` |
| **HIGH** | **Block, suggest manual** | `rm -rf`, `kill -9`, `shutdown`, `userdel` |
| **CRITICAL** | **Block, require approval** | `DROP DATABASE`, `terraform destroy`, `wipefs` |

Principle: **Better to over-block than to miss a threat.** Unmatched commands default to MEDIUM.

### File Protection (guard-files.sh)

Prevents the AI from tampering with its own safety controls:

| Zone | Protected Files | Write/Edit | Read |
|------|----------------|------------|------|
| **CRITICAL** | `.claude/settings.json`, all hook scripts | **DENY** | allow |
| **SENSITIVE** | `credentials.yaml`, `~/.ssh/id_*`, `engine.py`, `.env` | **DENY** | **ASK** |
| **CONFIG** | `~/.claude-safe-ops/config/*`, `settings.py` | **ASK** | allow |
| **NORMAL** | Everything else | allow | allow |

### Hook Integrity Verification (validate-hooks.sh)

On first invocation each session:
- Verifies all 4 hooks are registered in `.claude/settings.json`
- Checks all hook scripts exist and are executable
- Validates `credentials.yaml` has mode 600
- Warns if any safety component is missing or misconfigured

### Credential Security

| Rule | Implementation |
|------|---------------|
| No hardcoded passwords | Credentials via getpass or config file only |
| No passwords in logs | `SensitiveDataFilter` redacts all sensitive fields |
| No passwords in exceptions | `SSHConnectionError` strips credential info |
| File permissions | `credentials.yaml` enforced at mode 600 |
| Auth priority | Interactive input > env var > config file > SSH Agent |

### Audit Trail

Every remote operation is recorded in `~/.claude-safe-ops/audit/command_audit.jsonl`:

```json
{
  "timestamp": "2026-04-04T10:30:00+00:00",
  "host": "web-01",
  "command": "systemctl restart nginx",
  "risk_level": "MEDIUM",
  "status": "confirmed",
  "exit_code": 0,
  "operator": "haiqing",
  "matched_rules": ["Restart/reload service"]
}
```

Use `/audit` or `/audit summary` to review.

### Third-party Tool Coverage

The risk engine includes rules for common DevOps tools:

| Tool | High-risk Example | Level |
|------|-------------------|-------|
| Ansible | `ansible all -m shell --limit all` | CRITICAL |
| Terraform | `terraform destroy` | CRITICAL |
| Terraform | `terraform apply` | HIGH |
| Docker | `docker system prune` | HIGH |
| Kubernetes | `kubectl delete --all-namespaces` | CRITICAL |
| Puppet | `puppet cert clean` | HIGH |

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/onboard` | Guided first-time setup (check install, deps, SSH, hooks) |
| `/health` | Health check all servers + local environment |
| `/audit` | Query audit logs (filter by host, risk, time) |
| `/risk <cmd>` | Preview risk assessment without executing |
| `/playbook` | Manage and run ops playbooks |
| `/lang` | Switch CLI output language |

## Modules

| Module | Capabilities |
|--------|-------------|
| system | System info, CPU/memory/load, service management, users, crontab |
| network | Interfaces/routes/DNS, ping/traceroute, ports, firewall |
| disk | Disk/inode usage, LVM, SMART health, IO stats, large file finder |
| process | Process sorting/search/tree, kill, lsof, vmstat |
| deploy | App status, file upload, backup & rollback, health check |
| backup | Directory backup, DB export (MySQL/PG), scheduled backup, cleanup |
| security | Port audit, failed logins, sudo logs, SSH config, SUID scan |
| log | tail/search, syslog/dmesg, logrotate, error statistics |
| playbook | Ops playbooks: save and reuse verified workflows |

## Playbooks

Save verified operations as reusable playbooks:

```
CsOps> playbook
CsOps/playbook> list
CsOps/playbook> run restart-service service=nginx port=80
CsOps/playbook> save my-check
```

| Playbook | Purpose |
|----------|---------|
| restart-service | Service restart (status check -> config validation -> restart -> verify) |
| disk-cleanup | Disk cleanup (large files -> logs -> package cache -> confirm freed) |
| high-load-diagnose | High load diagnosis (CPU -> memory -> IO -> processes -> network) |
| ssh-bruteforce-check | SSH brute-force detection (failed logins -> IP stats -> security config) |
| mysql-slow-query | MySQL slow query diagnosis (slow queries -> processes -> table locks -> connections) |
| **macos-cleanup** | **macOS system & AI cache cleanup** (Claude/ChatGPT/Ollama/HuggingFace + npm/pip/Homebrew/Go + logs) |

Each playbook step still passes through the risk engine — safety is never bypassed.

## File Isolation

**Your data and project code are fully separated** — `git pull` never overwrites your config:

```
claude-safe-ops/                          ~/.claude-safe-ops/ (your private data)
├── src/          # Code               ├── config/
├── scripts/      # Safety hooks       │   ├── hosts.yaml         ← Server inventory
├── .claude/      # Hook registration  │   ├── credentials.yaml   ← SSH credentials (600)
│   └── commands/ # Slash commands     │   └── risk_rules.yaml    ← Custom rules (optional)
├── install.sh                         ├── playbooks/             ← User playbooks
└── CLAUDE.md                          ├── audit/                 ← Audit logs
                                       └── session/               ← Current connection
```

## Custom Risk Rules

Add rules in `~/.claude-safe-ops/config/risk_rules.yaml` (overrides built-in rules):

```yaml
rules:
  - pattern: "\\bmy-critical-app\\b"
    risk_level: HIGH
    description: "Involves critical business application"
```

## Language / i18n

```bash
export CSOPS_LANG=zh    # Chinese
export CSOPS_LANG=ko    # Korean
export CSOPS_LANG=en    # English (default)
export CSOPS_LANG=auto  # Auto-detect from system locale
```

Available: `en`, `zh`, `ko`. To add a new language, copy `src/config/locales/en.yaml` to `{lang}.yaml` and translate — zero code changes.

In Claude Code mode, the AI automatically detects your language and matches output accordingly.

## Prerequisites

| Dependency | Purpose | Required |
|------------|---------|----------|
| python3 | CLI mode + precise risk evaluation | Recommended (hooks fall back to shell without it) |
| jq | Hook JSON parsing | Yes |
| paramiko | SSH connection (pip) | CLI mode |
| pyyaml | YAML parsing (pip) | Yes |

## License

Apache License 2.0 — see [LICENSE](LICENSE)
