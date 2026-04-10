# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClaudeSafeOps — A server operations automation tool. Connects to remote servers via SSH to perform ops tasks, with a built-in risk assessment engine (115 rules) that forcibly blocks high-risk operations.

**Two usage modes**:
- **Claude Code mode** (recommended): Users launch Claude in this project directory and operate servers using natural language. Hooks automatically intercept dangerous commands.
- **Python CLI mode**: `python3 -m src.main` interactive command line.

## File Isolation (Key Design)

Project code and user data are fully isolated:

```
Project repo (git-managed, shared)                User data (~/.claude-safe-ops/, private)
───────────────────────────────        ─────────────────────────────
claude-safe-ops/                              ~/.claude-safe-ops/
├── src/              # Python source       ├── config/
├── scripts/          # Hook scripts        │   ├── hosts.yaml         # Server inventory
│   ├── risk-check.sh # Risk assessment     │   ├── credentials.yaml   # Credentials (mode 600)
│   ├── audit-log.sh  # Audit logging       │   └── risk_rules.yaml    # Custom rules (optional)
│   └── _risk_eval.py # Rule evaluator      ├── audit/
├── reports/          # Generated reports   │   └── command_audit.jsonl # Audit log
├── .claude/                                ├── session/
│   └── settings.json # Hooks registration  │   └── current_host.json  # Current session
├── CLAUDE.md         # This file           └── logs/
└── install.sh        # One-click install
```

**Rules**:
- All user data paths in the code point to `~/.claude-safe-ops/`; never create user files inside the project directory
- Config loading priority: user custom (`~/.claude-safe-ops/config/`) > project defaults (`src/config/`)
- `install.sh` initializes the `~/.claude-safe-ops/` directory and copies config templates

## SSH Connection Optimization (Claude Code Mode)

In Claude Code mode, commands are executed via Bash `ssh` calls. To avoid reconnecting on every command, the project uses **SSH ControlMaster** for OS-level connection multiplexing:

```
# ~/.ssh/config (added by install.sh)
Host *
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
```

**How it works**:
- First `ssh` call establishes a master connection and creates a Unix socket in `~/.ssh/sockets/`
- Subsequent `ssh` calls to the same host reuse the master connection (no re-authentication)
- `ControlPersist 600` keeps the master alive for 10 minutes after the last session ends
- This replaces the Python-level connection pool (`SSHConnectionManager`) which only works in CLI mode

**Claude Code should use SSH config aliases** (e.g., `ssh twms 'command'`) instead of full `ssh -i key user@host` to benefit from ControlMaster. Host aliases are defined in `~/.ssh/config` and should match entries in `~/.claude-safe-ops/config/hosts.yaml`.

## Server Metadata Cache

To avoid re-probing a host on every interaction, first-connect info is cached at:

```
~/.claude-safe-ops/cache/hosts/<alias>.json
```

Each file holds:
- `fingerprint` — OS, kernel, CPU, memory, disks, uptime, running services (TTL 24h)
- `software`    — detected software with version, binary path, config files, conf/data/log dirs, systemd unit, running status (TTL 12h)

**Claude Code usage convention**: before the *first* operation on a host within a session, run:

```bash
bash scripts/host-info.sh <alias>                # read cache, auto-refresh if stale
bash scripts/host-info.sh <alias> --force        # force re-collect
```

Use the JSON output to ground subsequent suggestions — e.g. "nginx config is at `/etc/nginx/nginx.conf`" comes from the cache rather than re-running probes. The software probe list is defined in `src/config/software_probes.yaml` and can be fully overridden by `~/.claude-safe-ops/config/software_probes.yaml` to add custom internal services.

In Python CLI mode, `HostSession.load_metadata()` performs the same lookup automatically on `connect` and prints a one-line summary.

## Onboarding (First-time Setup Guide)

When a user launches Claude Code in this project directory, check the following conditions to guide setup:

1. **`~/.claude-safe-ops/` does not exist** -> suggest running `./install.sh`
2. **`~/.claude-safe-ops/config/hosts.yaml` still has template defaults** -> guide user to add real servers
3. **SSH ControlMaster** -> verify `~/.ssh/sockets/` exists and `ControlMaster auto` is in `~/.ssh/config`
4. **SSH connectivity** -> help user test `ssh -o ConnectTimeout=5 -o BatchMode=yes user@host 'echo ok'`
5. **Everything ready** -> start accepting ops commands directly

## Architecture

```
src/
├── connection/     # SSH connection management (pool, keys, retry)
├── executor/       # Command execution engine (risk interception, approval flow)
│   ├── command_executor.py  # Core executor
│   └── session.py           # HostSession (simplified host-bound interface)
├── risk/           # Risk assessment engine (115 built-in rules + YAML extensions)
├── inventory/      # Server assets (loaded from ~/.claude-safe-ops/config/hosts.yaml)
├── modules/        # Nine ops modules (all execute via HostSession, never call connection directly)
│   ├── system/     network/     disk/        process/
│   ├── deploy/     backup/      security/    log/
│   └── playbook/   # Ops playbooks (save/reuse verified ops procedures)
├── utils/          # Logging (sensitive info filtering), formatted output, report generator
└── config/         # Settings constants, example config templates, built-in playbooks
```

## Risk Levels

| Level | Execution | Hook Behavior | Examples |
|------|----------|-----------|------|
| **LOW** | Auto-execute | exit 0 (allow) | `df -h`, `ps aux`, `uptime` |
| **MEDIUM** | Execute after confirmation | permissionDecision: ask | `systemctl restart`, `chmod` |
| **HIGH** | **Force manual** | permissionDecision: deny | `rm -rf`, `shutdown`, `kill -9` |
| **CRITICAL** | **Requires approval flow** | permissionDecision: deny | `DROP DATABASE`, batch operations |

Principle: **Better to over-block than to miss a threat.** Unmatched commands default to MEDIUM.

## Credential Security

- Credentials are only allowed via: runtime interactive input (getpass) or external config file (`~/.claude-safe-ops/config/credentials.yaml`, mode 600)
- **Forbidden**: hardcoding, logging output, passing passwords via command-line arguments
- Credential priority: interactive input > environment variables > config file > SSH Agent

## Key Constraints

- Modules execute commands through `HostSession`; direct calls to `connection` are not permitted
- All remote commands are written to the audit log (`~/.claude-safe-ops/audit/command_audit.jsonl`)
- `scripts/risk-check.sh` (PreToolUse hook) is the last line of defense; it takes effect even if the code layer fails to intercept
- No user configs, credentials, or log files are stored inside the project directory

## Security Hooks (Defense in Depth)

Five hooks registered in `.claude/settings.json` provide layered protection:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `sensitive-input-guard.sh` | UserPromptSubmit | Block passwords/tokens/keys in chat messages before they reach the AI API |
| `validate-hooks.sh` | PreToolUse (Bash) | Verify all hooks are registered + scripts exist + credentials permissions on first invocation |
| `risk-check.sh` | PreToolUse (Bash) | Assess SSH/remote command risk (115 rules), block HIGH/CRITICAL |
| `guard-files.sh` | PreToolUse (Write/Edit/Read/Glob) | Protect sensitive files from unauthorized access |
| `audit-log.sh` | PostToolUse (Bash) | Record all remote operations to audit log |

### guard-files.sh Protection Zones

| Zone | Protected Files | Write/Edit | Read |
|------|----------------|------------|------|
| **CRITICAL** | `.claude/settings.json`, hook scripts (`scripts/*.sh`) | **DENY** | allow |
| **SENSITIVE** | `credentials.yaml`, `~/.ssh/id_*`, `engine.py`, `.env` | **DENY** | **ASK** |
| **CONFIG** | `~/.claude-safe-ops/config/*`, `settings.py` | **ASK** | allow |
| **NORMAL** | Everything else | allow | allow |

This prevents:
- Disabling hooks by editing `.claude/settings.json`
- Modifying risk engine rules to bypass safety checks
- Reading credentials or SSH private keys without user approval
- Silently altering config files

## Third-party Tool Integration

The risk engine covers Ansible / Terraform / Puppet command patterns:

| Tool | High-risk Command Example | Risk Level |
|------|-------------|----------|
| Ansible | `ansible all -m shell --limit all` | CRITICAL |
| Terraform | `terraform destroy` | CRITICAL |
| Terraform | `terraform apply` | HIGH |
| Puppet | `puppet cert clean` | HIGH |

## Playbook (Ops Playbooks)

Users can save verified ops procedures as YAML playbooks for reuse when the same scenario arises.

**Storage locations**:
- Built-in playbooks: `src/config/playbooks/` (shipped with the project, 5 common scenarios)
- User playbooks: `~/.claude-safe-ops/playbooks/` (user-created, same name overrides built-in)

**Built-in playbooks**: restart-service, disk-cleanup, high-load-diagnose, ssh-bruteforce-check, mysql-slow-query

**CLI usage** (`use playbook` or `playbook` shortcut command):
- `list [tag]` -- list playbooks
- `show <name>` -- view details
- `run <name> [var=value ...]` -- execute playbook (requires host connection first)
- `save <name>` -- create playbook from recent operation history
- `delete <name>` -- delete a user playbook

**Claude Code mode**:
- User says "restart nginx using the previous procedure" -> find and execute matching playbook
- User says "save what we just did" -> guide through the save flow
- Proactively suggest existing playbooks when common scenarios are encountered

**Security**: Each step in a playbook still goes through the risk engine; security mechanisms are never bypassed.

## Report Generation

Operations that produce diagnostic results, incident analysis, or audit summaries can be saved as structured Markdown reports to `./reports/` (project directory, gitignored by default).

**File naming**: `{type}-{host}-{YYYYMMDD}-{HHMMSS}.md` (e.g., `incident-web-01-20260410-143022.md`)

### Analysis Reports (结果型)

| Type | Use Case | Default Sections |
|------|----------|-----------------|
| `incident` | Post-mortem / fault analysis | Summary, Environment, Symptoms, Root Cause, Impact, Remediation, Recommendations, Reference Data |
| `audit-summary` | Audit log analysis | Summary, Time Range, Command Stats, Risk Distribution, High-Risk Commands, Top Operators |
| `health-check` | System health snapshot | Summary, System Overview, CPU & Memory, Disk Usage, Services, Security Checks, Recommendations |
| `diagnostic` | Troubleshooting record | Summary, Environment, Symptoms, Investigation, Findings, Recommendations |

### Process Documentation (过程型)

When the user asks Claude to document their operation process, write an operation guide, or record what was changed:

| Type | Use Case | Default Sections |
|------|----------|-----------------|
| `operation-log` | Record what was done during a session | Summary, Objective, Operation Timeline, Result Summary, Notes |
| `runbook` | Reusable step-by-step SOP | Overview, Prerequisites, Operation Steps (with commands + expected output), Verification, Rollback Plan |
| `change-record` | Document what changed and why | Summary, Change Reason, Change Scope, Operation Timeline, Before/After Comparison, Verification |
| `custom` | Anything else | User-defined |

**When to generate which document**:
- User says "帮我记录一下刚才的操作过程" → `operation-log` (操作记录)
- User says "写个操作说明以后可以复用" → `runbook` (操作说明/SOP)
- User says "帮我写个变更记录" → `change-record` (变更记录)
- User says "写个故障报告" → `incident` (故障报告)

### Usage

**Python CLI mode** (via `ReportBuilder`):
```python
from src.utils.report import ReportBuilder, ReportType

report = (
    ReportBuilder(ReportType.INCIDENT, title="nginx OOM crash")
    .meta(host="web-01", severity="P1")
    .section("故障现象", symptoms_md)
    .section("根因分析", rca_md)
    .build()
)
path = report.save()
```

**Process documentation from audit log** (auto-generates from command history):
```python
from src.utils.report import generate_operation_log, generate_runbook, generate_change_record
from src.executor.command_executor import AuditLogger

records = AuditLogger().query(host="web-01", limit=30)

# Operation log — chronological record of what was done
report = generate_operation_log(records, objective="恢复 diciai 服务")

# Runbook — cleaned-up reusable SOP (only successful commands become steps)
report = generate_runbook(records, overview="OOM 后恢复 app 进程", rollback="docker restart diciai")

# Change record — what changed, why, before/after
report = generate_change_record(records, change_reason="OOM 导致全站不可用", before_state="9098 无监听", after_state="HTTP 200")

path = report.save()
```

**Claude Code mode**: Claude composes the Markdown naturally during investigation, then calls `save_report()` to persist:
```python
from src.utils.report import save_report
path = save_report(content, report_type="operation-log", host="web-01")
```

**Markdown helpers**: `md_table(headers, rows)` and `md_kv(data)` generate clean Markdown tables (no ANSI escapes) suitable for file output, complementing the terminal-focused `print_table()` / `print_kv()` in `output.py`.

## Internationalization (i18n)

The CLI supports multiple languages via YAML locale files.

**Language selection** (priority order):
1. `CSOPS_LANG` environment variable (e.g., `CSOPS_LANG=zh`, `CSOPS_LANG=ko`)
2. `CSOPS_LANG=auto` (default) — auto-detect from system locale (`LC_ALL`, `LC_MESSAGES`, `LANG`)
3. Fallback: `en`

**Runtime switching**: Call `set_lang("zh")` from `src.utils.i18n` to switch language without restart.

**Locale files**: `src/config/locales/{lang}.yaml`
- `en.yaml` — English (default + fallback)
- `zh.yaml` — Chinese
- `ko.yaml` — Korean

**Adding a new language**: Copy `en.yaml` to `{lang}.yaml`, translate the values. No code changes needed.

**For developers**: Use `t("key.subkey", var=value)` from `src.utils.i18n` for all user-facing strings. Keys use dot notation matching the YAML structure. Fallback to English if a key is missing in the current locale.

## Claude Code Mode — Auto Language Detection

When operating in Claude Code mode, Claude should **automatically match the user's language**:

- If the user speaks Chinese, set `CSOPS_LANG=zh` before running commands
- If the user speaks Korean, set `CSOPS_LANG=ko` before running commands
- If the user speaks English (or unknown), use the default `en`

This ensures CLI output (risk warnings, execution feedback, etc.) matches the language the user is communicating in.
