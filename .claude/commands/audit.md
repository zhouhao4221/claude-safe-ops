# /audit — Review Audit Logs

Review and analyze the ClaudeSafeOps operation audit trail.

## Arguments

The user may provide optional filters after `/audit`:
- `/audit` — show last 20 records
- `/audit 50` — show last 50 records  
- `/audit host=web-01` — filter by host
- `/audit risk=HIGH` — filter by risk level
- `/audit today` — filter today's records
- `/audit summary` — show statistics summary

## How to execute

1. Read `~/.claude-safe-ops/audit/command_audit.jsonl` (each line is a JSON record)
2. Each record has fields: `timestamp`, `host`, `command`, `risk_level`, `status`, `exit_code`, `operator`, `matched_rules`
3. Apply any filters the user specified
4. Display results in a formatted table

## Output format

### Default (recent records)
```
Time                Host      Risk     Status    Command
2026-04-04 10:30    web-01    LOW      executed  df -h
2026-04-04 10:31    web-01    MEDIUM   confirmed systemctl restart nginx
2026-04-04 10:32    db-01     HIGH     refused   rm -rf /var/log/*
```

### Summary mode (`/audit summary`)
```
=== Audit Summary ===
Total operations: 142
Period: 2026-03-20 ~ 2026-04-04

By risk level:
  LOW        98  (69%)
  MEDIUM     35  (25%)
  HIGH        7  (5%)   ← 3 refused, 4 manual
  CRITICAL    2  (1%)   ← all refused

By host:
  web-01     85 operations
  db-01      42 operations
  app-01     15 operations

Recent HIGH/CRITICAL (last 5):
  2026-04-04 10:32  db-01   rm -rf /var/log/*     HIGH     refused
  ...
```
