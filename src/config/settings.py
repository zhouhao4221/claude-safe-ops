"""
Global configuration and constants

System-level settings including risk level enum, default paths, logging config, and SSH parameters.
"""

from enum import IntEnum
from pathlib import Path

# ─── Risk level enum ───────────────────────────────────────────────────────────────

class RiskLevel(IntEnum):
    """Command risk level; higher value = higher risk"""
    LOW = 1       # Read-only / informational commands
    MEDIUM = 2    # Reversible change operations
    HIGH = 3      # Irreversible or high-impact operations
    CRITICAL = 4  # Batch/destructive operations, requires approval

    @property
    def label(self) -> str:
        labels = {
            RiskLevel.LOW: "Low Risk",
            RiskLevel.MEDIUM: "Medium Risk",
            RiskLevel.HIGH: "High Risk",
            RiskLevel.CRITICAL: "Critical Risk",
        }
        return labels[self]

    @property
    def color(self) -> str:
        """ANSI color code for terminal output"""
        colors = {
            RiskLevel.LOW: "\033[92m",       # green
            RiskLevel.MEDIUM: "\033[93m",    # yellow
            RiskLevel.HIGH: "\033[91m",      # red
            RiskLevel.CRITICAL: "\033[95m",  # purple
        }
        return colors[self]


# ─── Path layout ────────────────────────────────────────────────────────────────────
# Project code and user data are fully isolated:
#   Project repo (git): code + default rules
#   User dir (~/.claude-safe-ops/): host config, credentials, audit logs, custom rules

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# User data directory (private, not in git)
USER_DATA_DIR = Path.home() / ".claude-safe-ops"
USER_CONFIG_DIR = USER_DATA_DIR / "config"
USER_AUDIT_DIR = USER_DATA_DIR / "audit"
USER_SESSION_DIR = USER_DATA_DIR / "session"

# Project default config (read-only, shipped with code)
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "src" / "config"
DEFAULT_RISK_RULES_PATH = DEFAULT_CONFIG_DIR / "risk_rules.yaml"

# User config files (higher priority than defaults)
HOSTS_CONFIG_PATH = USER_CONFIG_DIR / "hosts.yaml"
RISK_RULES_CONFIG_PATH = USER_CONFIG_DIR / "risk_rules.yaml"
CREDENTIALS_CONFIG_PATH = USER_CONFIG_DIR / "credentials.yaml"
SESSION_FILE_PATH = USER_SESSION_DIR / "current_host.json"

# Playbook directories (built-in shipped with project; user custom in ~/.claude-safe-ops/)
DEFAULT_PLAYBOOK_DIR = DEFAULT_CONFIG_DIR / "playbooks"
USER_PLAYBOOK_DIR = USER_DATA_DIR / "playbooks"

# Log directories (under user data dir)
LOG_DIR = USER_DATA_DIR / "logs"
AUDIT_LOG_DIR = USER_AUDIT_DIR

# ─── Logging config ────────────────────────────────────────────────────────────────────

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
            "datefmt": "%H:%M:%S",
        },
        "file": {
            "format": "%(asctime)s [%(levelname)-7s] %(name)s %(filename)s:%(lineno)d - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
            "level": "INFO",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "ops_tool.log"),
            "formatter": "file",
            "level": "DEBUG",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
}

# ─── SSH defaults ─────────────────────────────────────────────────────────────────

SSH_DEFAULT_PORT = 22
SSH_CONNECT_TIMEOUT = 10          # Connect timeout (seconds)
SSH_COMMAND_TIMEOUT = 300         # Command timeout (seconds)
SSH_MAX_RETRIES = 3               # Max retries
SSH_RETRY_DELAY = 2               # Retry delay (seconds)
SSH_MAX_CONNECTIONS_PER_HOST = 5  # Max connections per host
SSH_KEEPALIVE_INTERVAL = 30       # Keepalive interval (seconds)

# ─── Audit log ────────────────────────────────────────────────────────────────────

AUDIT_LOG_PATH = AUDIT_LOG_DIR / "command_audit.jsonl"
AUDIT_LOG_MAX_SIZE = 50 * 1024 * 1024  # 50MB

# ─── Sensitive data filtering ─────────────────────────────────────────────────────

# Field names to redact in logs
SENSITIVE_FIELDS = frozenset({
    "password", "passwd", "secret", "token", "key",
    "passphrase", "credential", "auth", "private_key",
})

# Redaction placeholder
REDACTED_PLACEHOLDER = "***REDACTED***"
