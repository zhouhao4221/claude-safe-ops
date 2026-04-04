#!/usr/bin/env python3
"""
Minimal risk evaluator -- standalone, no project dependencies
Usage: echo "rm -rf /tmp" | python3 _risk_eval.py /path/to/risk-rules.yaml
Output: JSON {"risk_level": "HIGH", "matched_rules": ["recursive force delete"], "default": false}
"""

import json
import re
import sys
from pathlib import Path

import yaml


def load_rules(rules_path: str) -> tuple[list[dict], str]:
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", []), data.get("default_risk_level", "MEDIUM")


def evaluate(command: str, rules: list[dict], default_level: str) -> dict:
    command = command.strip()
    if not command:
        return {"risk_level": "LOW", "matched_rules": [], "default": False}

    level_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    max_level = "LOW"
    matched = []

    for rule in rules:
        try:
            if re.search(rule["pattern"], command, re.IGNORECASE):
                matched.append(rule["description"])
                if level_order.get(rule["risk_level"], 0) > level_order.get(max_level, 0):
                    max_level = rule["risk_level"]
        except re.error:
            continue

    if not matched:
        return {"risk_level": default_level, "matched_rules": [], "default": True}

    return {"risk_level": max_level, "matched_rules": matched, "default": False}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: echo 'command' | _risk_eval.py <rules.yaml>"}))
        sys.exit(1)

    rules_path = sys.argv[1]
    if not Path(rules_path).exists():
        print(json.dumps({"error": f"Rules file not found: {rules_path}"}))
        sys.exit(1)

    command = sys.stdin.read().strip()
    rules, default_level = load_rules(rules_path)
    result = evaluate(command, rules, default_level)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
