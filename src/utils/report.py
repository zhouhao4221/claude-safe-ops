"""Report generator module.

Generates structured Markdown reports and saves them to
``~/.claude-safe-ops/reports/``.  Supports multiple report types
(incident, audit summary, health check, diagnostic) with consistent
formatting, metadata headers, and table-of-contents generation.

Usage (Python CLI mode)::

    from src.utils.report import ReportBuilder, ReportType

    report = (
        ReportBuilder(ReportType.INCIDENT, title="nginx OOM crash")
        .meta(host="web-01", severity="P1", operator="ops-bot")
        .section("环境信息", env_table_md)
        .section("故障现象", symptoms_md)
        .section("根因分析", rca_md)
        .section("改进建议", recommendations_md)
        .build()
    )
    path = report.save()          # -> ~/.claude-safe-ops/reports/incident-web-01-20260410-143022.md
    print(report.render())        # -> full Markdown string

In Claude Code mode, Claude composes the Markdown naturally and calls
``save_report()`` to persist it.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.config.settings import REPORT_DIR

logger = logging.getLogger(__name__)


# ─── Report types ───────────────────────────────────────────────────────────

class ReportType(Enum):
    """Supported report types, each with a default section template."""

    INCIDENT = "incident"
    AUDIT_SUMMARY = "audit-summary"
    HEALTH_CHECK = "health-check"
    DIAGNOSTIC = "diagnostic"
    OPERATION_LOG = "operation-log"
    RUNBOOK = "runbook"
    CHANGE_RECORD = "change-record"
    CUSTOM = "custom"


# Default section templates per report type.
# Each entry is (section_key, i18n_key) — the i18n_key is looked up at
# render time so that the language can be switched dynamically.
_SECTION_TEMPLATES: Dict[ReportType, List[str]] = {
    ReportType.INCIDENT: [
        "report.section.summary",
        "report.section.environment",
        "report.section.symptoms",
        "report.section.root_cause",
        "report.section.impact",
        "report.section.remediation",
        "report.section.recommendations",
        "report.section.reference_data",
    ],
    ReportType.AUDIT_SUMMARY: [
        "report.section.summary",
        "report.section.time_range",
        "report.section.command_stats",
        "report.section.risk_distribution",
        "report.section.high_risk_commands",
        "report.section.top_operators",
    ],
    ReportType.HEALTH_CHECK: [
        "report.section.summary",
        "report.section.system_overview",
        "report.section.cpu_memory",
        "report.section.disk_usage",
        "report.section.services",
        "report.section.security_checks",
        "report.section.recommendations",
    ],
    ReportType.DIAGNOSTIC: [
        "report.section.summary",
        "report.section.environment",
        "report.section.symptoms",
        "report.section.investigation",
        "report.section.findings",
        "report.section.recommendations",
    ],
    ReportType.OPERATION_LOG: [
        "report.section.summary",
        "report.section.environment",
        "report.section.objective",
        "report.section.operation_timeline",
        "report.section.result_summary",
        "report.section.notes",
    ],
    ReportType.RUNBOOK: [
        "report.section.overview",
        "report.section.prerequisites",
        "report.section.operation_steps",
        "report.section.verification",
        "report.section.rollback",
        "report.section.notes",
    ],
    ReportType.CHANGE_RECORD: [
        "report.section.summary",
        "report.section.change_reason",
        "report.section.environment",
        "report.section.change_scope",
        "report.section.operation_timeline",
        "report.section.before_after",
        "report.section.verification",
        "report.section.notes",
    ],
}


# ─── Data structures ────────────────────────────────────────────────────────

@dataclass
class ReportSection:
    """A single section inside a report."""
    title: str
    content: str
    level: int = 2  # Markdown heading level (## by default)


@dataclass
class ReportMeta:
    """Metadata header rendered as a table at the top of the report."""
    report_type: ReportType
    title: str
    created_at: str = ""
    host: str = ""
    severity: str = ""
    operator: str = ""
    extras: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_local_iso()


@dataclass
class Report:
    """A fully assembled report, ready to render or save."""
    meta: ReportMeta
    sections: List[ReportSection]
    _report_dir: Path = field(default=REPORT_DIR, repr=False)

    def render(self) -> str:
        """Render the full Markdown document."""
        parts: List[str] = []

        # Title
        parts.append(f"# {self.meta.title}\n")

        # Metadata table
        parts.append(_render_meta_table(self.meta))

        # Table of contents
        if len(self.sections) > 2:
            parts.append(_render_toc(self.sections))

        # Sections with numbering
        for idx, section in enumerate(self.sections, 1):
            heading = "#" * section.level
            parts.append(f"{heading} {_cjk_num(idx)}、{section.title}\n")
            if section.content.strip():
                parts.append(section.content.strip())
            parts.append("")  # blank line after section

        # Footer
        parts.append("---\n")
        parts.append(
            f"> Generated by ClaudeSafeOps · {self.meta.created_at}"
        )

        return "\n\n".join(parts) + "\n"

    def save(self, filename: str = "", report_dir: Optional[Path] = None) -> Path:
        """Save the report to disk.

        Args:
            filename: Override filename (without directory). Auto-generated if empty.
            report_dir: Override output directory. Defaults to ``~/.claude-safe-ops/reports/``.

        Returns:
            The absolute path of the saved file.
        """
        out_dir = Path(report_dir) if report_dir else self._report_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = _generate_filename(self.meta)

        path = out_dir / filename
        path.write_text(self.render(), encoding="utf-8")
        logger.info("Report saved: %s", path)
        return path


# ─── Builder ────────────────────────────────────────────────────────────────

class ReportBuilder:
    """Fluent builder for assembling reports step by step.

    Example::

        report = (
            ReportBuilder(ReportType.INCIDENT, title="OOM crash")
            .meta(host="web-01", severity="P1")
            .section("故障现象", "服务 9098 端口无响应...")
            .section("根因分析", "容器内存无限制...")
            .build()
        )
    """

    def __init__(
        self,
        report_type: ReportType = ReportType.CUSTOM,
        title: str = "",
    ) -> None:
        self._type = report_type
        self._title = title or _default_title(report_type)
        self._host = ""
        self._severity = ""
        self._operator = ""
        self._extras: Dict[str, str] = {}
        self._sections: List[ReportSection] = []

    def meta(
        self,
        *,
        host: str = "",
        severity: str = "",
        operator: str = "",
        **extras: str,
    ) -> "ReportBuilder":
        """Set report metadata fields."""
        if host:
            self._host = host
        if severity:
            self._severity = severity
        if operator:
            self._operator = operator
        self._extras.update(extras)
        return self

    def section(
        self,
        title: str,
        content: str = "",
        level: int = 2,
    ) -> "ReportBuilder":
        """Append a section."""
        self._sections.append(ReportSection(title=title, content=content, level=level))
        return self

    def build(self) -> Report:
        """Assemble the final Report object."""
        report_meta = ReportMeta(
            report_type=self._type,
            title=self._title,
            host=self._host,
            severity=self._severity,
            operator=self._operator,
            extras=self._extras,
        )
        return Report(meta=report_meta, sections=list(self._sections))


# ─── Convenience functions for Claude Code mode ─────────────────────────────

def save_report(
    content: str,
    *,
    report_type: str = "custom",
    title: str = "",
    host: str = "",
    filename: str = "",
    report_dir: Optional[str] = None,
) -> Path:
    """Save a pre-composed Markdown string as a report file.

    This is the primary entry point in **Claude Code mode** where Claude
    composes the full Markdown body and just needs to persist it.

    Args:
        content: Full Markdown content to save.
        report_type: One of "incident", "audit-summary", "health-check",
                     "diagnostic", "custom".
        title: Report title (used in filename generation).
        host: Target host alias (used in filename generation).
        filename: Explicit filename override.
        report_dir: Override output directory.

    Returns:
        Path to the saved report file.
    """
    rtype = _parse_report_type(report_type)
    out_dir = Path(report_dir) if report_dir else REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        meta = ReportMeta(report_type=rtype, title=title or "report", host=host)
        filename = _generate_filename(meta)

    path = out_dir / filename
    path.write_text(content, encoding="utf-8")
    logger.info("Report saved: %s", path)
    return path


def list_reports(report_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """List saved reports, newest first.

    Returns a list of dicts with keys: filename, path, size, modified.
    """
    out_dir = Path(report_dir) if report_dir else REPORT_DIR
    if not out_dir.exists():
        return []

    reports: List[Dict[str, Any]] = []
    for p in sorted(out_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = p.stat()
        reports.append({
            "filename": p.name,
            "path": str(p),
            "size": _human_size(stat.st_size),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return reports


# ─── Process documentation generators ───────────────────────────────────────

def generate_operation_log(
    records: List[Dict[str, Any]],
    *,
    title: str = "",
    host: str = "",
    operator: str = "",
    objective: str = "",
    notes: str = "",
) -> Report:
    """Generate an operation log from audit records.

    Reads a list of audit record dicts (as returned by ``AuditLogger.query()``)
    and produces a structured chronological operation document.

    Args:
        records: Audit record dicts (timestamp, host, command, risk_level,
                 status, stdout, stderr, exit_code).
        title: Document title override.
        host: Target host (auto-detected from records if empty).
        operator: Operator name (auto-detected from records if empty).
        objective: Free-text description of what the operation aimed to achieve.
        notes: Additional notes or observations.

    Returns:
        A ``Report`` ready to ``.render()`` or ``.save()``.
    """
    from src.utils.i18n import t

    if not host:
        hosts = {r.get("host", "") for r in records if r.get("host")}
        host = ", ".join(sorted(hosts)) if hosts else ""
    if not operator:
        ops = {r.get("operator", "") for r in records if r.get("operator")}
        operator = ", ".join(sorted(ops)) if ops else ""

    # Time range
    timestamps = [r.get("timestamp", "") for r in records if r.get("timestamp")]
    time_start = min(timestamps) if timestamps else ""
    time_end = max(timestamps) if timestamps else ""

    # Stats
    total = len(records)
    succeeded = sum(1 for r in records if r.get("exit_code") == 0)
    failed = sum(1 for r in records if r.get("exit_code", -1) not in (0, -1))
    blocked = sum(1 for r in records if r.get("status") in ("blocked", "refused"))

    builder = ReportBuilder(
        ReportType.OPERATION_LOG,
        title=title or t("report.type.operation-log"),
    ).meta(host=host, operator=operator)

    if time_start:
        builder.meta(**{t("report.meta.time_range"): f"{time_start} ~ {time_end}"})

    # Section: Summary
    summary_data = {
        t("report.meta.host"): host or "-",
        t("report.meta.operator"): operator or "-",
        t("report.meta.time_range"): f"{time_start} ~ {time_end}" if time_start else "-",
        t("report.stats.total_commands"): str(total),
        t("report.stats.succeeded"): str(succeeded),
        t("report.stats.failed"): str(failed),
        t("report.stats.blocked"): str(blocked),
    }
    builder.section(t("report.section.summary"), md_kv(summary_data))

    # Section: Objective
    if objective:
        builder.section(t("report.section.objective"), objective)

    # Section: Operation Timeline
    if records:
        timeline_rows = []
        for r in records:
            ts = r.get("timestamp", "")
            # Shorten timestamp for display: keep HH:MM:SS
            short_ts = ts.split("T")[-1][:8] if "T" in ts else ts[-8:] if len(ts) > 8 else ts
            cmd = r.get("command", "")
            # Truncate long commands
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            risk = r.get("risk_level", "")
            status = r.get("status", "")
            exit_code = r.get("exit_code", -1)

            # Status icon
            if status in ("blocked", "refused"):
                status_display = f"🚫 {status}"
            elif exit_code == 0:
                status_display = "✅"
            elif exit_code > 0:
                status_display = f"❌ exit={exit_code}"
            else:
                status_display = status

            timeline_rows.append([short_ts, cmd, risk, status_display])

        builder.section(
            t("report.section.operation_timeline"),
            md_table(
                [t("table.time"), t("table.command"), t("table.risk"), t("table.status")],
                timeline_rows,
            ),
        )

    # Section: Result Summary
    if failed > 0 or blocked > 0:
        failed_cmds = [
            r for r in records
            if r.get("exit_code", -1) not in (0, -1) or r.get("status") in ("blocked", "refused")
        ]
        if failed_cmds:
            fail_rows = []
            for r in failed_cmds:
                cmd = r.get("command", "")[:60]
                reason = r.get("reason", "") or r.get("stderr", "")[:100]
                fail_rows.append([cmd, r.get("status", ""), reason])
            builder.section(
                t("report.section.result_summary"),
                md_table(
                    [t("table.command"), t("table.status"), t("report.section.reason")],
                    fail_rows,
                ),
            )
    else:
        builder.section(
            t("report.section.result_summary"),
            t("report.stats.all_succeeded", total=total),
        )

    # Section: Notes
    if notes:
        builder.section(t("report.section.notes"), notes)

    return builder.build()


def generate_runbook(
    records: List[Dict[str, Any]],
    *,
    title: str = "",
    host: str = "",
    overview: str = "",
    prerequisites: str = "",
    verification: str = "",
    rollback: str = "",
    notes: str = "",
) -> Report:
    """Generate a reusable runbook/SOP from audit records.

    Transforms raw command history into a clean, repeatable procedure
    document with prerequisites, numbered steps, verification, and rollback.

    Args:
        records: Audit record dicts. Only ``executed``/``confirmed`` commands
                 with ``exit_code == 0`` are included as steps by default.
        title: Document title override.
        host: Target host description (e.g., "production web servers").
        overview: What this procedure accomplishes.
        prerequisites: Pre-conditions before starting (free Markdown).
        verification: How to verify the operation succeeded (free Markdown).
        rollback: Rollback steps if something goes wrong (free Markdown).
        notes: Additional caveats or tips.

    Returns:
        A ``Report`` ready to ``.render()`` or ``.save()``.
    """
    from src.utils.i18n import t

    # Filter to successful commands only — a runbook should describe the happy path
    ok_records = [
        r for r in records
        if r.get("status") in ("executed", "confirmed") and r.get("exit_code", -1) == 0
    ]

    builder = ReportBuilder(
        ReportType.RUNBOOK,
        title=title or t("report.type.runbook"),
    ).meta(host=host)

    # Section: Overview
    builder.section(t("report.section.overview"), overview or t("report.placeholder.overview"))

    # Section: Prerequisites
    pre_lines = []
    if host:
        pre_lines.append(f"- {t('report.prereq.host_access', host=host)}")
    # Detect risk levels — warn if any MEDIUM+ commands exist
    risk_levels = {r.get("risk_level", "") for r in ok_records}
    if risk_levels & {"MEDIUM", "HIGH", "CRITICAL"}:
        pre_lines.append(f"- {t('report.prereq.risk_warning')}")
    if prerequisites:
        pre_lines.append(prerequisites)
    builder.section(
        t("report.section.prerequisites"),
        "\n".join(pre_lines) if pre_lines else t("report.placeholder.prerequisites"),
    )

    # Section: Operation Steps
    if ok_records:
        step_lines = []
        for idx, r in enumerate(ok_records, 1):
            cmd = r.get("command", "")
            risk = r.get("risk_level", "LOW")
            risk_tag = f" `[{risk}]`" if risk != "LOW" else ""

            step_lines.append(f"### {t('report.step_prefix', n=idx)}{risk_tag}\n")
            step_lines.append(f"```bash\n{cmd}\n```\n")

            # Add output hint if it's short enough to be useful
            stdout = (r.get("stdout") or "").strip()
            if stdout and len(stdout) < 500:
                step_lines.append(f"{t('report.expected_output')}:\n")
                # Truncate at 5 lines for readability
                out_lines = stdout.splitlines()[:5]
                preview = "\n".join(out_lines)
                if len(stdout.splitlines()) > 5:
                    preview += f"\n... ({len(stdout.splitlines()) - 5} more lines)"
                step_lines.append(f"```\n{preview}\n```\n")

        builder.section(t("report.section.operation_steps"), "\n".join(step_lines))
    else:
        builder.section(t("report.section.operation_steps"), t("report.placeholder.no_steps"))

    # Section: Verification
    builder.section(
        t("report.section.verification"),
        verification or t("report.placeholder.verification"),
    )

    # Section: Rollback
    builder.section(
        t("report.section.rollback"),
        rollback or t("report.placeholder.rollback"),
    )

    # Section: Notes
    if notes:
        builder.section(t("report.section.notes"), notes)

    return builder.build()


def generate_change_record(
    records: List[Dict[str, Any]],
    *,
    title: str = "",
    host: str = "",
    operator: str = "",
    change_reason: str = "",
    change_scope: str = "",
    before_state: str = "",
    after_state: str = "",
    verification: str = "",
    notes: str = "",
) -> Report:
    """Generate a change record documenting what was changed and why.

    Args:
        records: Audit record dicts.
        title: Document title override.
        host: Target host.
        operator: Who performed the change.
        change_reason: Why the change was needed.
        change_scope: What systems/services are affected.
        before_state: Description or snapshot of the state before the change.
        after_state: Description or snapshot of the state after the change.
        verification: How the change was verified.
        notes: Additional notes.

    Returns:
        A ``Report`` ready to ``.render()`` or ``.save()``.
    """
    from src.utils.i18n import t

    if not host:
        hosts = {r.get("host", "") for r in records if r.get("host")}
        host = ", ".join(sorted(hosts)) if hosts else ""
    if not operator:
        ops = {r.get("operator", "") for r in records if r.get("operator")}
        operator = ", ".join(sorted(ops)) if ops else ""

    timestamps = [r.get("timestamp", "") for r in records if r.get("timestamp")]
    time_start = min(timestamps) if timestamps else ""
    time_end = max(timestamps) if timestamps else ""

    builder = ReportBuilder(
        ReportType.CHANGE_RECORD,
        title=title or t("report.type.change-record"),
    ).meta(host=host, operator=operator)

    if time_start:
        builder.meta(**{t("report.meta.time_range"): f"{time_start} ~ {time_end}"})

    # Section: Summary
    summary_data = {
        t("report.meta.host"): host or "-",
        t("report.meta.operator"): operator or "-",
        t("report.meta.time_range"): f"{time_start} ~ {time_end}" if time_start else "-",
        t("report.change.total_operations"): str(len(records)),
    }
    builder.section(t("report.section.summary"), md_kv(summary_data))

    # Section: Change Reason
    builder.section(
        t("report.section.change_reason"),
        change_reason or t("report.placeholder.change_reason"),
    )

    # Section: Change Scope
    if change_scope:
        builder.section(t("report.section.change_scope"), change_scope)

    # Section: Operation Timeline (same as operation log)
    if records:
        timeline_rows = []
        for r in records:
            ts = r.get("timestamp", "")
            short_ts = ts.split("T")[-1][:8] if "T" in ts else ts[-8:] if len(ts) > 8 else ts
            cmd = r.get("command", "")
            if len(cmd) > 80:
                cmd = cmd[:77] + "..."
            exit_code = r.get("exit_code", -1)
            status_display = "✅" if exit_code == 0 else f"❌ exit={exit_code}" if exit_code > 0 else r.get("status", "")
            timeline_rows.append([short_ts, cmd, status_display])

        builder.section(
            t("report.section.operation_timeline"),
            md_table(
                [t("table.time"), t("table.command"), t("table.status")],
                timeline_rows,
            ),
        )

    # Section: Before / After
    if before_state or after_state:
        ba_parts = []
        if before_state:
            ba_parts.append(f"**{t('report.change.before')}**\n\n{before_state}")
        if after_state:
            ba_parts.append(f"**{t('report.change.after')}**\n\n{after_state}")
        builder.section(t("report.section.before_after"), "\n\n---\n\n".join(ba_parts))

    # Section: Verification
    if verification:
        builder.section(t("report.section.verification"), verification)

    # Section: Notes
    if notes:
        builder.section(t("report.section.notes"), notes)

    return builder.build()


# ─── Markdown helpers ───────────────────────────────────────────────────────

def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a Markdown table (no ANSI, suitable for file output).

    Args:
        headers: Column header strings.
        rows: 2D list of cell values.

    Returns:
        A Markdown-formatted table string.
    """
    if not headers:
        return ""

    str_rows = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def _pad(cells: Sequence[str]) -> str:
        return "| " + " | ".join(
            str(c).ljust(widths[i]) if i < len(widths) else str(c)
            for i, c in enumerate(cells)
        ) + " |"

    lines = [
        _pad(headers),
        "|" + "|".join("-" * (w + 2) for w in widths) + "|",
    ]
    for row in str_rows:
        lines.append(_pad(row))

    return "\n".join(lines)


def md_kv(data: Dict[str, str], bold_keys: bool = True) -> str:
    """Render a key-value Markdown table (two columns: item + value).

    Args:
        data: Ordered dict of key-value pairs.
        bold_keys: Whether to bold the key column.

    Returns:
        A Markdown table string.
    """
    headers = ["项目", "内容"]
    rows = []
    for k, v in data.items():
        key_cell = f"**{k}**" if bold_keys else k
        rows.append([key_cell, v])
    return md_table(headers, rows)


# ─── Internal helpers ───────────────────────────────────────────────────────

def _now_local_iso() -> str:
    """Current local time in ISO-like format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _generate_filename(meta: ReportMeta) -> str:
    """Generate a report filename: {type}-{host}-{timestamp}.md"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    parts = [meta.report_type.value]
    if meta.host:
        parts.append(_safe_name(meta.host))
    parts.append(ts)
    return "-".join(parts) + ".md"


_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    """Sanitize a string for use in filenames."""
    return _UNSAFE_RE.sub("_", name.strip()) or "unknown"


def _default_title(rtype: ReportType) -> str:
    """Fallback title when none is provided."""
    from src.utils.i18n import t
    return t(f"report.type.{rtype.value}")


def _parse_report_type(value: str) -> ReportType:
    """Parse a string into a ReportType enum."""
    mapping = {t.value: t for t in ReportType}
    return mapping.get(value.lower().strip(), ReportType.CUSTOM)


def _render_meta_table(meta: ReportMeta) -> str:
    """Render the metadata header as a Markdown table."""
    from src.utils.i18n import t

    rows: Dict[str, str] = {}
    rows[t("report.meta.type")] = t(f"report.type.{meta.report_type.value}")
    rows[t("report.meta.created_at")] = meta.created_at
    if meta.host:
        rows[t("report.meta.host")] = meta.host
    if meta.severity:
        rows[t("report.meta.severity")] = meta.severity
    if meta.operator:
        rows[t("report.meta.operator")] = meta.operator
    for k, v in meta.extras.items():
        rows[k] = v

    return md_kv(rows)


def _render_toc(sections: List[ReportSection]) -> str:
    """Render a table of contents from section titles."""
    lines = ["**目录**\n"]
    for idx, sec in enumerate(sections, 1):
        anchor = _slugify(f"{_cjk_num(idx)}、{sec.title}")
        lines.append(f"{idx}. [{sec.title}](#{anchor})")
    return "\n".join(lines)


def _slugify(text: str) -> str:
    """Convert a heading to a GitHub-compatible anchor slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return text


def _cjk_num(n: int) -> str:
    """Convert 1-10 to CJK numeral for section numbering."""
    cjk = "一二三四五六七八九十"
    if 1 <= n <= 10:
        return cjk[n - 1]
    return str(n)


def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"
