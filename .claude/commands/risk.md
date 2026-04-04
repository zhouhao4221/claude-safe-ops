# /risk — Test Command Risk Assessment

Evaluate the risk level of a command without executing it. Helps users understand what would happen before running a command.

## Arguments

`/risk <command>` — the command to evaluate

Examples:
- `/risk rm -rf /var/log/old`
- `/risk systemctl restart nginx`
- `/risk DROP DATABASE production`
- `/risk df -h`

## How to execute

1. Run the Python risk engine to evaluate the command:
   ```bash
   echo "<command>" | python3 scripts/_risk_eval.py src/config/risk_rules.yaml
   ```
   Also check if user has custom rules at `~/.claude-safe-ops/config/risk_rules.yaml` and use those instead if they exist.

2. Parse the JSON result: `{"risk_level": "...", "matched_rules": [...], "default": bool}`

3. Display the result with clear visual indicators:

## Output format

```
Command:  rm -rf /var/log/old
Risk:     🔴 HIGH
Rules:    Recursive force delete

Action:   BLOCKED — must be executed manually on the target host.
          This command will NOT be auto-executed by ClaudeSafeOps.
```

```
Command:  systemctl restart nginx
Risk:     🟡 MEDIUM
Rules:    Restart/reload service

Action:   CONFIRM — you will be prompted before execution.
```

```
Command:  df -h
Risk:     🟢 LOW
Rules:    View disk usage

Action:   AUTO — will execute automatically without confirmation.
```

For HIGH and CRITICAL commands, also suggest safer alternatives when possible:
- `rm -rf` → suggest reviewing files first with `ls -la` or using `find ... -delete` with confirmation
- `kill -9` → suggest `kill` (SIGTERM) first
- `DROP DATABASE` → suggest backup first
