"""
Command execution engine

Handles risk assessment, execution decisions, and audit logging.
Execution strategy:
  - LOW: auto-execute
  - MEDIUM: confirm before execution
  - HIGH: refuse, print manual command
  - CRITICAL: refuse, require approval workflow
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config.settings import (
    RiskLevel,
    AUDIT_LOG_PATH,
    AUDIT_LOG_DIR,
    REDACTED_PLACEHOLDER,
)
from src.connection.ssh_client import SSHConfig, SSHConnectionManager
from src.risk.engine import RiskEngine, RiskRule
from src.utils.i18n import t
from src.utils.output import (
    bold, colorize, confirm_prompt, error, header, info,
    print_kv, risk_badge, separator, success, warning,
    RED, GREEN, YELLOW, MAGENTA, CYAN,
)

logger = logging.getLogger(__name__)


@dataclass
class CommandRecord:
    """Command execution record"""
    timestamp: str
    host: str
    command: str
    risk_level: str
    status: str           # executed | confirmed | blocked | refused
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    operator: str = ""
    matched_rules: list[str] = field(default_factory=list)
    reason: str = ""

    def to_audit_dict(self) -> dict:
        """Convert to audit log dict (filter sensitive fields)"""
        d = asdict(self)
        # Truncate overly long output
        for key in ("stdout", "stderr"):
            if len(d[key]) > 4096:
                d[key] = d[key][:4096] + "...(truncated)"
        return d


class AuditLogger:
    """
    Audit logger

    Writes audit logs in JSON Lines format, thread-safe.
    """

    def __init__(self, log_path: Path = AUDIT_LOG_PATH) -> None:
        self._log_path = log_path
        self._lock = threading.Lock()
        AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def log(self, record: CommandRecord) -> None:
        """Write an audit record"""
        with self._lock:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    json.dump(
                        record.to_audit_dict(),
                        f,
                        ensure_ascii=False,
                        default=str,
                    )
                    f.write("\n")
            except Exception:
                logger.exception("Failed to write audit log")

    def query(
        self,
        host: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query recent audit records"""
        if not self._log_path.exists():
            return []

        records: list[dict] = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if host and rec.get("host") != host:
                        continue
                    records.append(rec)
                except json.JSONDecodeError:
                    continue

        return records[-limit:]


class CommandExecutor:
    """
    Command execution engine

    Integrates risk assessment, connection management, execution strategy, and audit logging.
    """

    def __init__(
        self,
        ssh_manager: Optional[SSHConnectionManager] = None,
        risk_engine: Optional[RiskEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        operator: Optional[str] = None,
    ) -> None:
        self._ssh = ssh_manager or SSHConnectionManager()
        self._risk_engine = risk_engine or RiskEngine()
        self._audit = audit_logger or AuditLogger()
        self._operator = operator or os.getenv("USER", "unknown")

    def execute(
        self,
        ssh_config: SSHConfig,
        command: str,
    ) -> CommandRecord:
        """
        Assess and execute a command

        Execution strategy by risk level:
          LOW      -> auto-execute
          MEDIUM   -> interactive confirmation
          HIGH     -> refuse, print manual command
          CRITICAL -> refuse, require approval workflow

        Returns:
            CommandRecord execution record
        """
        host = ssh_config.host
        risk_level, matched_rules = self._risk_engine.evaluate(command)
        rule_descs = [r.description for r in matched_rules]

        # Display risk assessment result
        print(header(t("executor.risk_title")))
        print(print_kv({
            t("executor.target_host"): host,
            t("executor.command"): command,
            t("executor.risk_level"): risk_badge(risk_level),
            t("executor.matched_rules"): ", ".join(rule_descs) if rule_descs else t("executor.no_rules"),
        }))
        print(separator())

        now = datetime.now(timezone.utc).isoformat()
        base_record = CommandRecord(
            timestamp=now,
            host=host,
            command=command,
            risk_level=risk_level.name,
            status="pending",
            operator=self._operator,
            matched_rules=rule_descs,
        )

        # Execute based on risk level
        if risk_level == RiskLevel.LOW:
            return self._auto_execute(ssh_config, command, base_record)

        elif risk_level == RiskLevel.MEDIUM:
            return self._confirm_execute(ssh_config, command, base_record)

        elif risk_level == RiskLevel.HIGH:
            return self._refuse_high(ssh_config, command, base_record)

        else:  # CRITICAL
            return self._refuse_critical(ssh_config, command, base_record)

    def _auto_execute(
        self,
        ssh_config: SSHConfig,
        command: str,
        record: CommandRecord,
    ) -> CommandRecord:
        """LOW risk: auto-execute"""
        print(info(t("executor.low_auto")))
        return self._do_execute(ssh_config, command, record)

    def _confirm_execute(
        self,
        ssh_config: SSHConfig,
        command: str,
        record: CommandRecord,
    ) -> CommandRecord:
        """MEDIUM risk: requires user confirmation"""
        print(warning(t("executor.medium_confirm")))

        if confirm_prompt(t("executor.confirm_exec", host=ssh_config.host)):
            record.status = "confirmed"
            return self._do_execute(ssh_config, command, record)
        else:
            record.status = "blocked"
            record.reason = t("executor.cancelled")
            print(info(t("executor.exec_cancelled")))
            self._audit.log(record)
            return record

    def _refuse_high(
        self,
        ssh_config: SSHConfig,
        command: str,
        record: CommandRecord,
    ) -> CommandRecord:
        """HIGH risk: refuse auto-execution, print manual command"""
        record.status = "refused"
        record.reason = t("executor.high_reason")

        print(error(t("executor.high_refused")))
        print()
        print(colorize(t("executor.high_manual"), YELLOW))
        print(f"  {bold(command)}")
        print()
        print(colorize(f"  ssh {ssh_config.username}@{ssh_config.host} -p {ssh_config.port}", CYAN))
        print()

        logger.warning(
            "Refused high-risk command [%s@%s]: %s",
            self._operator, ssh_config.host, command,
        )
        self._audit.log(record)
        return record

    def _refuse_critical(
        self,
        ssh_config: SSHConfig,
        command: str,
        record: CommandRecord,
    ) -> CommandRecord:
        """CRITICAL risk: refuse execution, require approval workflow"""
        record.status = "refused"
        record.reason = t("executor.critical_reason")

        print(colorize(t("executor.critical_banner"), MAGENTA))
        print(error(t("executor.critical_refused")))
        print()
        print(colorize(t("executor.critical_process"), YELLOW))
        print(f"  {t('executor.critical_step1')}")
        print(f"  {t('executor.critical_step2')}")
        print(f"  {t('executor.critical_step3')}")
        print(f"  {t('executor.critical_step4')}")
        print()

        logger.critical(
            "Refused critical-risk command [%s@%s]: %s",
            self._operator, ssh_config.host, command,
        )
        self._audit.log(record)
        return record

    def _do_execute(
        self,
        ssh_config: SSHConfig,
        command: str,
        record: CommandRecord,
    ) -> CommandRecord:
        """Actually execute the command"""
        try:
            exit_code, stdout, stderr = self._ssh.execute_command(
                ssh_config, command
            )
            record.exit_code = exit_code
            record.stdout = stdout
            record.stderr = stderr
            record.status = "executed" if record.status == "pending" else record.status

            if exit_code == 0:
                print(success(t("executor.cmd_success")))
            else:
                print(warning(t("executor.cmd_done", code=exit_code)))

            if stdout.strip():
                print(f"\n{bold('stdout:')}")
                print(stdout.rstrip())

            if stderr.strip():
                print(f"\n{colorize('stderr:', RED)}")
                print(stderr.rstrip())

        except Exception as e:
            record.status = "error"
            record.reason = str(e)
            print(error(t("executor.exec_err", error=e)))
            logger.error("Command execution error [%s]: %s", ssh_config.host, type(e).__name__)

        self._audit.log(record)
        return record

    @property
    def audit_logger(self) -> AuditLogger:
        return self._audit
