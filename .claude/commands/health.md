# /health — System Health Check

Run a quick health check on the ClaudeSafeOps environment and all configured servers.

## What to check

### Local environment
1. **Hook scripts**: Verify all 4 scripts exist and are executable (`scripts/risk-check.sh`, `scripts/audit-log.sh`, `scripts/guard-files.sh`, `scripts/validate-hooks.sh`)
2. **Hook registration**: Parse `.claude/settings.json` and confirm all hooks are registered
3. **Credentials file permissions**: Check `~/.claude-safe-ops/config/credentials.yaml` is mode 600
4. **Audit log**: Check if `~/.claude-safe-ops/audit/command_audit.jsonl` exists, report its size and last entry timestamp
5. **Python modules**: Run `python3 -c "import paramiko, yaml"` to verify dependencies

### Remote servers
For each host in `~/.claude-safe-ops/config/hosts.yaml`:
1. Test SSH connectivity: `ssh -o ConnectTimeout=5 -o BatchMode=yes user@host 'echo ok'`
2. If reachable, also grab: `uptime`, `df -h / | tail -1`, `free -h | grep Mem` (or equivalent for the OS)

### Output
Present results as a clear dashboard:
```
=== ClaudeSafeOps Health Check ===

Local:
  ✓ Hooks          4/4 registered and executable
  ✓ Credentials    mode 600
  ✓ Audit log      12.3 KB, last entry 2026-04-04 10:30:00
  ✓ Dependencies   paramiko, pyyaml OK

Servers:
  ✓ web-01     up 30d, disk 45%, mem 62%
  ✗ db-01      SSH timeout
  ✓ app-01     up 5d, disk 12%, mem 35%
```

If any check fails, provide actionable fix instructions.
