"""Terminal output utilities

Table rendering, status indicators, separators, and other terminal display helpers.
"""

from __future__ import annotations

import shutil
from typing import Any, Sequence

from src.config.settings import RiskLevel


# ─── ANSI colors ───────────────────────────────────────────────────────────────────

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


def colorize(text: str, color: str) -> str:
    """Colorize text"""
    return f"{color}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}"


# ─── Status indicators ───────────────────────────────────────────────────────────────────

def success(msg: str) -> str:
    return f"{GREEN}[OK]{RESET} {msg}"


def warning(msg: str) -> str:
    return f"{YELLOW}[WARN]{RESET} {msg}"


def error(msg: str) -> str:
    return f"{RED}[ERROR]{RESET} {msg}"


def info(msg: str) -> str:
    return f"{CYAN}[INFO]{RESET} {msg}"


def risk_badge(level: RiskLevel) -> str:
    """Render risk level badge"""
    from src.utils.i18n import t
    _risk_keys = {
        RiskLevel.LOW: "risk.low",
        RiskLevel.MEDIUM: "risk.medium",
        RiskLevel.HIGH: "risk.high",
        RiskLevel.CRITICAL: "risk.critical",
    }
    label = t(_risk_keys.get(level, "risk.medium"))
    return f"{level.color}[{label}]{RESET}"


# ─── Separators ──────────────────────────────────────────────────────────────────────

def separator(char: str = "-", width: int | None = None) -> str:
    """Generate a separator line"""
    if width is None:
        width = min(shutil.get_terminal_size().columns, 80)
    return char * width


def header(title: str, char: str = "=", width: int | None = None) -> str:
    """Generate a header line with title"""
    if width is None:
        width = min(shutil.get_terminal_size().columns, 80)
    side_len = max((width - len(title) - 2) // 2, 1)
    line = f"{char * side_len} {BOLD}{title}{RESET} {char * side_len}"
    return line


# ─── Table output ────────────────────────────────────────────────────────────────────

def print_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    min_col_width: int = 6,
    max_col_width: int = 50,
) -> str:
    """
    Render a simple terminal table

    Args:
        headers: Column header list
        rows: Data rows (2D list)
        min_col_width: Minimum column width
        max_col_width: Maximum column width

    Returns:
        Formatted table string
    """
    if not headers:
        return ""

    num_cols = len(headers)

    # Calculate column widths
    col_widths: list[int] = []
    for i in range(num_cols):
        max_w = len(str(headers[i]))
        for row in rows:
            if i < len(row):
                # Calculate display width after stripping ANSI escapes
                cell_text = _strip_ansi(str(row[i]))
                max_w = max(max_w, len(cell_text))
        col_widths.append(max(min(max_w, max_col_width), min_col_width))

    lines: list[str] = []

    # Header
    header_line = " | ".join(
        f"{BOLD}{str(h).ljust(col_widths[i])}{RESET}"
        for i, h in enumerate(headers)
    )
    lines.append(header_line)

    # Separator
    sep = "-+-".join("-" * w for w in col_widths)
    lines.append(sep)

    # Data rows
    for row in rows:
        cells: list[str] = []
        for i in range(num_cols):
            val = str(row[i]) if i < len(row) else ""
            display_len = len(_strip_ansi(val))
            # Padding spaces (accounting for ANSI escape width)
            padding = col_widths[i] - display_len
            cells.append(val + " " * max(padding, 0))
        lines.append(" | ".join(cells))

    return "\n".join(lines)


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences for display width calculation"""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ─── Key-value display ───────────────────────────────────────────────────────────────────

def print_kv(data: dict[str, Any], indent: int = 2, key_width: int = 20) -> str:
    """
    Render a key-value list

    Args:
        data: Key-value dict
        indent: Indentation spaces
        key_width: Key alignment width
    """
    lines: list[str] = []
    prefix = " " * indent
    for k, v in data.items():
        key_str = f"{CYAN}{str(k).ljust(key_width)}{RESET}"
        lines.append(f"{prefix}{key_str}: {v}")
    return "\n".join(lines)


# ─── Confirmation prompt ─────────────────────────────────────────────────────────────────

def confirm_prompt(message: str) -> bool:
    """
    Interactive confirmation prompt

    Returns:
        True if user confirms, False if cancelled
    """
    prompt_text = f"{YELLOW}[?]{RESET} {message} [{GREEN}y{RESET}/{RED}N{RESET}]: "
    try:
        answer = input(prompt_text).strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
