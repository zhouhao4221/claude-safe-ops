"""
Risk assessment engine

Evaluates command strings against risk rules, supports built-in rules and custom YAML rules.
Design principle: better to over-block than under-block (unmatched commands default to MEDIUM).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.config.settings import RiskLevel, RISK_RULES_CONFIG_PATH, DEFAULT_RISK_RULES_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskRule:
    """Risk rule definition"""
    pattern: str           # Regex pattern
    risk_level: RiskLevel  # Risk level
    description: str       # Rule description
    _compiled: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", re.compile(self.pattern, re.IGNORECASE))

    def matches(self, command: str) -> bool:
        """Check if a command matches this rule"""
        return bool(self._compiled.search(command))


# ─── Built-in rules ────────────────────────────────────────────────────────────────────

def _build_default_rules() -> list[RiskRule]:
    """Build the default risk rule set"""
    rules: list[RiskRule] = []

    # === CRITICAL: batch/destructive operations ===
    critical_patterns = [
        (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$", "Delete root directory"),
        (r"\brm\s+-rf\s+/\s*$", "Recursive force delete root directory"),
        (r"\bDROP\s+DATABASE\b", "Drop database"),
        (r"\bTRUNCATE\s+TABLE\b", "Truncate table"),
        (r"\bformat\s+/dev/", "Format disk device"),
        (r"\bwipefs\b", "Wipe filesystem signatures"),
        (r"\bkubectl\s+delete\s+.*--all-namespaces", "Cluster-wide K8s resource deletion"),
        (r"\bkubectl\s+delete\s+namespace\b", "Delete K8s namespace"),
        (r"\betcdctl\s+del\b", "Delete etcd keys"),
        (r"\bfor\s+.*\b(ssh|ansible)\b.*\bdone\b", "Batch remote execution loop"),
        (r"\bansible\s+.*-m\s+(shell|command|raw)\b.*--limit\s+all", "Ansible full-scope execution"),
    ]
    for pat, desc in critical_patterns:
        rules.append(RiskRule(pattern=pat, risk_level=RiskLevel.CRITICAL, description=desc))

    # === HIGH: irreversible or high-impact operations ===
    high_patterns = [
        (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f", "Recursive force delete"),
        (r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r", "Recursive force delete"),
        (r"\bfdisk\b", "Disk partitioning"),
        (r"\bmkfs\b", "Create filesystem"),
        (r"\bdd\s+", "Low-level disk copy"),
        (r"\biptables\s+-F\b", "Flush firewall rules"),
        (r"\biptables\s+.*-D\b", "Delete firewall rule"),
        (r"\bsystemctl\s+stop\s+(sshd|network|firewalld|iptables|docker|kubelet)\b",
         "Stop critical system service"),
        (r"\bkill\s+-9\b", "Force kill process"),
        (r"\bkillall\s+-9\b", "Force kill all processes by name"),
        (r"\bdocker\s+rm\s+-f\b", "Force remove Docker container"),
        (r"\bdocker\s+system\s+prune\b", "Docker system prune"),
        (r"\bkubectl\s+delete\b", "Delete K8s resource"),
        (r"\buserdel\b", "Delete user"),
        (r"\bpasswd\b", "Change password"),
        (r"\bshutdown\b", "Shutdown"),
        (r"\breboot\b", "Reboot"),
        (r"\binit\s+[06]\b", "Change runlevel (shutdown/reboot)"),
        (r"\bparted\b", "Disk partitioning (parted)"),
        (r"\blvremove\b", "Remove logical volume"),
        (r"\bvgremove\b", "Remove volume group"),
        (r"\bpvremove\b", "Remove physical volume"),
    ]
    for pat, desc in high_patterns:
        rules.append(RiskRule(pattern=pat, risk_level=RiskLevel.HIGH, description=desc))

    # === MEDIUM: reversible change operations ===
    medium_patterns = [
        (r"\bsystemctl\s+(restart|reload)\b", "Restart/reload service"),
        (r"\bservice\s+\S+\s+(restart|reload)\b", "Restart/reload service"),
        (r"\bcrontab\s+-e\b", "Edit crontab"),
        (r"\buseradd\b", "Add user"),
        (r"\bgroupadd\b", "Add user group"),
        (r"\bchmod\b", "Change file permissions"),
        (r"\bchown\b", "Change file ownership"),
        (r"\bdocker\s+restart\b", "Restart Docker container"),
        (r"\bdocker\s+stop\b", "Stop Docker container"),
        (r"\bdocker\s+start\b", "Start Docker container"),
        (r"\bkubectl\s+scale\b", "Scale K8s replicas"),
        (r"\bkubectl\s+apply\b", "Apply K8s config"),
        (r"\bkubectl\s+rollout\b", "K8s rollout"),
        (r"\byum\s+install\b", "YUM install package"),
        (r"\bapt(-get)?\s+install\b", "APT install package"),
        (r"\bdnf\s+install\b", "DNF install package"),
        (r"\bpip\s+install\b", "PIP install package"),
        (r"\bsed\s+-i\b", "In-place file edit"),
        (r"\bvi\s+\b", "Edit file"),
        (r"\bvim\s+\b", "Edit file"),
        (r"\bnano\s+\b", "Edit file"),
        (r"\bmkdir\b", "Create directory"),
        (r"\bcp\s+", "Copy file"),
        (r"\bmv\s+", "Move/rename file"),
        (r"\bln\s+", "Create link"),
        (r"\btee\s+", "Write to file"),
    ]
    for pat, desc in medium_patterns:
        rules.append(RiskRule(pattern=pat, risk_level=RiskLevel.MEDIUM, description=desc))

    # === LOW: read-only / informational ===
    low_patterns = [
        (r"^\s*ls\b", "List directory contents"),
        (r"^\s*ll\b", "List directory contents (detailed)"),
        (r"^\s*cat\b", "View file contents"),
        (r"^\s*less\b", "View file (pager)"),
        (r"^\s*more\b", "View file (pager)"),
        (r"^\s*df\b", "View disk usage"),
        (r"^\s*free\b", "View memory usage"),
        (r"^\s*uptime\b", "View uptime"),
        (r"^\s*ps\b", "View process list"),
        (r"^\s*top\b", "View system load"),
        (r"^\s*htop\b", "View system load"),
        (r"^\s*netstat\b", "View network connections"),
        (r"^\s*ss\b", "View socket statistics"),
        (r"^\s*ip\s+addr\b", "View IP addresses"),
        (r"^\s*ip\s+a\b", "View IP addresses"),
        (r"^\s*ifconfig\b", "View network interfaces"),
        (r"^\s*hostname\b", "View hostname"),
        (r"^\s*whoami\b", "View current user"),
        (r"^\s*date\b", "View system time"),
        (r"^\s*w\b", "View logged-in users"),
        (r"^\s*last\b", "View login history"),
        (r"^\s*head\b", "View file head"),
        (r"^\s*tail\b", "View file tail"),
        (r"^\s*grep\b", "Text search"),
        (r"^\s*egrep\b", "Extended regex search"),
        (r"^\s*find\b", "Find files"),
        (r"^\s*locate\b", "Locate files"),
        (r"^\s*du\b", "View directory size"),
        (r"^\s*mount\s*$", "View mount points (read-only)"),
        (r"^\s*lsblk\b", "View block devices"),
        (r"^\s*blkid\b", "View block device IDs"),
        (r"^\s*systemctl\s+status\b", "View service status"),
        (r"^\s*systemctl\s+list-units\b", "List system services"),
        (r"^\s*journalctl\b", "View system journal"),
        (r"^\s*dmesg\b", "View kernel log"),
        (r"^\s*docker\s+ps\b", "View Docker containers"),
        (r"^\s*docker\s+images\b", "View Docker images"),
        (r"^\s*docker\s+logs\b", "View Docker logs"),
        (r"^\s*docker\s+inspect\b", "View Docker details"),
        (r"^\s*kubectl\s+get\b", "View K8s resources"),
        (r"^\s*kubectl\s+describe\b", "Describe K8s resource"),
        (r"^\s*kubectl\s+logs\b", "View K8s logs"),
        (r"^\s*kubectl\s+top\b", "View K8s resource usage"),
        (r"^\s*uname\b", "View system info"),
        (r"^\s*id\b", "View user ID"),
        (r"^\s*env\b", "View environment variables"),
        (r"^\s*echo\b", "Print text"),
        (r"^\s*ping\b", "Network connectivity test"),
        (r"^\s*traceroute\b", "Traceroute"),
        (r"^\s*nslookup\b", "DNS lookup"),
        (r"^\s*dig\b", "DNS lookup"),
        (r"^\s*curl\b.*--head\b", "HTTP HEAD request"),
        (r"^\s*wc\b", "Count lines/words"),
        (r"^\s*sort\b", "Sort"),
        (r"^\s*uniq\b", "Deduplicate"),
        (r"^\s*awk\b", "Text processing"),
    ]
    for pat, desc in low_patterns:
        rules.append(RiskRule(pattern=pat, risk_level=RiskLevel.LOW, description=desc))

    return rules


class RiskEngine:
    """
    Risk assessment engine

    Matches command strings against rules and returns the highest risk level.
    Returns MEDIUM by default when no rules match (better to over-block than under-block).
    """

    def __init__(self, custom_rules_path: Optional[Path] = None) -> None:
        self._rules: list[RiskRule] = _build_default_rules()

        # Rule loading priority: user custom > project default YAML > built-in Python rules
        # 1. Project default YAML rules (extends built-in rules)
        if DEFAULT_RISK_RULES_PATH.exists():
            self._load_custom_rules(DEFAULT_RISK_RULES_PATH)
            logger.info("Loaded project default rules: %s", DEFAULT_RISK_RULES_PATH)

        # 2. User custom rules (~/.claude-safe-ops/config/risk_rules.yaml, highest priority)
        user_rules = custom_rules_path or RISK_RULES_CONFIG_PATH
        if user_rules.exists():
            self._load_custom_rules(user_rules)
            logger.info("Loaded user custom rules: %s", user_rules)

    def _load_custom_rules(self, path: Path) -> None:
        """Load custom rules from YAML file, prepended for higher priority"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "rules" not in data:
                return

            custom: list[RiskRule] = []
            for item in data["rules"]:
                level = RiskLevel[item["risk_level"].upper()]
                rule = RiskRule(
                    pattern=item["pattern"],
                    risk_level=level,
                    description=item.get("description", "Custom rule"),
                )
                custom.append(rule)

            # Prepend custom rules for higher priority
            self._rules = custom + self._rules
            logger.debug("Loaded %d custom risk rules", len(custom))

        except Exception:
            logger.exception("Failed to load custom risk rules: %s", path)

    def evaluate(self, command: str) -> tuple[RiskLevel, list[RiskRule]]:
        """
        Evaluate the risk level of a command

        Returns:
            (highest risk level, list of matched rules)
            Returns (MEDIUM, []) when no rules match
        """
        command = command.strip()
        if not command:
            return RiskLevel.LOW, []

        matched_rules: list[RiskRule] = []
        max_level = RiskLevel.LOW

        for rule in self._rules:
            if rule.matches(command):
                matched_rules.append(rule)
                if rule.risk_level > max_level:
                    max_level = rule.risk_level

        # Unknown commands default to MEDIUM (better to over-block)
        if not matched_rules:
            logger.debug("No rules matched, defaulting to MEDIUM: %s", command)
            return RiskLevel.MEDIUM, []

        logger.debug(
            "Command [%s] assessed as %s, matched %d rules",
            command, max_level.label, len(matched_rules),
        )
        return max_level, matched_rules

    def add_rule(self, rule: RiskRule) -> None:
        """Dynamically add a rule"""
        self._rules.insert(0, rule)

    @property
    def rules(self) -> list[RiskRule]:
        """Get all current rules (read-only copy)"""
        return list(self._rules)
