# /playbook — Playbook Operations

Manage and execute ops playbooks — saved, reusable operation workflows.

## Arguments

- `/playbook` or `/playbook list` — list all available playbooks
- `/playbook show <name>` — show playbook details and steps
- `/playbook run <name> [var=value ...]` — execute a playbook on the connected host
- `/playbook save <name>` — create a playbook from recent operations

## How to execute

### list
1. Scan built-in playbooks at `src/config/playbooks/*.yaml`
2. Scan user playbooks at `~/.claude-safe-ops/playbooks/*.yaml`
3. Display as a table with name, description, tags, and source (built-in/user)

### show <name>
1. Find the playbook YAML (user dir takes precedence over built-in)
2. Display: description, tags, variables with defaults, each step (name + command), and notes

### run <name>
1. Confirm a host is connected (user must have mentioned a host or connected earlier in conversation)
2. Load the playbook, substitute variables
3. Show the execution plan (all steps with resolved commands)
4. Ask for confirmation before executing
5. Execute each step via SSH, showing progress
6. For each step: show command, execute, report success/failure
7. If a step fails and `on_fail` is not "continue", stop and report
8. Show final summary table

### save <name>
1. Read recent audit log entries from `~/.claude-safe-ops/audit/command_audit.jsonl`
2. Show recent executed commands for the user to select from
3. Ask for description and tags
4. Generate a YAML playbook file in `~/.claude-safe-ops/playbooks/`
5. Suggest the user review and add variables ({{var}}) for parameterization

## Playbook YAML format
```yaml
name: restart-service
description: "General service restart workflow"
tags: [service, restart]
vars:
  service: nginx
  port: "80"
steps:
  - name: Check current service status
    command: "systemctl status {{service}}"
  - name: Restart service
    command: "systemctl restart {{service}}"
  - name: Verify port is listening
    command: "ss -tlnp | grep :{{port}}"
notes: |
  Ensure config is valid before restarting.
```
