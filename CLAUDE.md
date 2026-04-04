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
├── .claude/                                │   └── command_audit.jsonl # Audit log
│   └── settings.json # Hooks registration  ├── session/
├── CLAUDE.md         # This file           │   └── current_host.json  # Current session
└── install.sh        # One-click install   └── logs/
```

**Rules**:
- All user data paths in the code point to `~/.claude-safe-ops/`; never create user files inside the project directory
- Config loading priority: user custom (`~/.claude-safe-ops/config/`) > project defaults (`src/config/`)
- `install.sh` initializes the `~/.claude-safe-ops/` directory and copies config templates

## Onboarding (First-time Setup Guide)

When a user launches Claude Code in this project directory, check the following conditions to guide setup:

1. **`~/.claude-safe-ops/` does not exist** -> suggest running `./install.sh`
2. **`~/.claude-safe-ops/config/hosts.yaml` still has template defaults** -> guide user to add real servers
3. **SSH connectivity** -> help user test `ssh -o ConnectTimeout=5 -o BatchMode=yes user@host 'echo ok'`
4. **Everything ready** -> start accepting ops commands directly

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
├── utils/          # Logging (sensitive info filtering), formatted output
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

Four hooks registered in `.claude/settings.json` provide layered protection:

| Hook | Trigger | Purpose |
|------|---------|---------|
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
