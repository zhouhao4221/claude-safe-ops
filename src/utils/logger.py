"""Logging utilities

Colored console output, audit file logging, and built-in sensitive data filtering.
"""

from __future__ import annotations

import logging
import logging.config
import re
from pathlib import Path
from typing import Any

from src.config.settings import (
    LOG_DIR,
    AUDIT_LOG_DIR,
    LOGGING_CONFIG,
    SENSITIVE_FIELDS,
    REDACTED_PLACEHOLDER,
)


class SensitiveDataFilter(logging.Filter):
    """Log filter: auto-redact sensitive data

    Detects sensitive fields (password, token, secret, etc.) in log messages
    and replaces their values with ***REDACTED***.
    """

    # Match key=value, key: value, or "key": "value" patterns
    _PATTERNS = [
        re.compile(
            rf'(?i)(["\']?(?:{"|".join(SENSITIVE_FIELDS)})["\']?\s*[:=]\s*)(["\']?)(\S+?)(\2)(?=[\s,;}})\]$]|$)'
        ),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self._PATTERNS:
                record.msg = pattern.sub(
                    rf"\1\2{REDACTED_PLACEHOLDER}\4", record.msg
                )
        # Redact sensitive content in args
        if record.args:
            record.args = self._redact_args(record.args)
        return True

    def _redact_args(self, args: Any) -> Any:
        """Recursively redact log arguments"""
        if isinstance(args, dict):
            return {
                k: REDACTED_PLACEHOLDER if self._is_sensitive_key(k) else v
                for k, v in args.items()
            }
        if isinstance(args, (tuple, list)):
            return tuple(
                REDACTED_PLACEHOLDER if isinstance(a, str) and self._contains_sensitive(a) else a
                for a in args
            )
        return args

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        return key.lower() in SENSITIVE_FIELDS

    @staticmethod
    def _contains_sensitive(text: str) -> bool:
        lower = text.lower()
        return any(field in lower for field in SENSITIVE_FIELDS)


# ─── ANSI color constants ───────────────────────────────────────────────────────────────

class Colors:
    """Terminal ANSI color codes"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"


class ColoredFormatter(logging.Formatter):
    """Colored console log formatter"""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.DIM,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: f"{Colors.BOLD}{Colors.RED}",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        record.levelname = f"{color}{record.levelname:<7}{Colors.RESET}"
        return super().format(record)


def setup_logging() -> None:
    """Initialize logging system

    Ensures log directories exist, configures colored console output and file logging,
    and attaches sensitive data filters to all handlers.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(LOGGING_CONFIG)

    # Add sensitive data filter to all handlers
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)

    # Set colored formatter for console handler
    for handler in logging.root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setFormatter(
                ColoredFormatter(
                    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                )
            )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by module name"""
    return logging.getLogger(name)
