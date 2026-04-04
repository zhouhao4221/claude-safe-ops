# /onboard — First-time Setup Guide

Run the onboarding checklist for ClaudeSafeOps. Check each step and guide the user through any missing setup.

## Steps

1. **Check installation**: Verify `~/.claude-safe-ops/` directory exists with required subdirectories (config/, audit/, session/, logs/, playbooks/). If missing, suggest running `./install.sh`.

2. **Check dependencies**: Run `python3 --version` and `jq --version`. Report any missing dependencies.

3. **Check host config**: Read `~/.claude-safe-ops/config/hosts.yaml`. If it still contains the example template content (hostname: web-01, ip: 192.168.1.10), tell the user they need to add their real servers. Show them the format.

4. **Check credentials permissions**: If `~/.claude-safe-ops/config/credentials.yaml` exists, run `stat -f '%A' ~/.claude-safe-ops/config/credentials.yaml` (macOS) or `stat -c '%a'` (Linux) and verify it's 600. Warn if not.

5. **Test SSH connectivity**: For each host in hosts.yaml, test with:
   ```
   ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no user@host 'echo ok'
   ```
   Report which hosts are reachable and which failed.

6. **Check hooks integrity**: Verify `.claude/settings.json` has all 4 hooks registered (validate-hooks, risk-check, guard-files, audit-log). Verify all scripts in `scripts/` are executable.

7. **Print summary**: Show a status table with checkmarks/crosses for each step. If everything passes, tell the user they're ready to go.

## Output format

Use a clear status table, e.g.:
```
✓ Installation     ~/.claude-safe-ops/ exists
✓ Dependencies     python3 3.12, jq 1.7
✗ Host config      Still using template defaults
✓ Credentials      permissions 600
✗ SSH: web-01      Connection refused
✓ Hooks            All 4 hooks registered
```
