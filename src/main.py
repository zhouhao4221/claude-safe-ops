"""
ClaudeSafeOps — Server ops automation tool

Interactive CLI entry point for remote server operations.
"""

from __future__ import annotations

import sys

from src.utils.i18n import t, init_i18n
from src.utils.logger import setup_logging, get_logger
from src.utils.output import (
    bold, colorize, header, separator, print_table, risk_badge,
    success, warning, error, info, confirm_prompt,
    GREEN, CYAN, YELLOW, RED, DIM, RESET,
)
from src.config.settings import RiskLevel
from src.connection.ssh_client import SSHConfig, SSHConnectionManager
from src.executor.command_executor import CommandExecutor
from src.executor.session import HostSession
from src.risk.engine import RiskEngine
from src.inventory.hosts import HostInventory

from src.modules.system import SystemOps
from src.modules.network import NetworkOps
from src.modules.disk import DiskOps
from src.modules.process import ProcessOps
from src.modules.deploy import DeployOps
from src.modules.backup import BackupOps
from src.modules.security import SecurityOps
from src.modules.log import LogOps
from src.modules.playbook import PlaybookOps

logger = get_logger(__name__)

def _get_module_registry() -> dict:
    """Build module registry with translated descriptions (call after init_i18n)."""
    return {
        "system":   (SystemOps,   t("module.system")),
        "network":  (NetworkOps,  t("module.network")),
        "disk":     (DiskOps,     t("module.disk")),
        "process":  (ProcessOps,  t("module.process")),
        "deploy":   (DeployOps,   t("module.deploy")),
        "backup":   (BackupOps,   t("module.backup")),
        "security": (SecurityOps, t("module.security")),
        "log":      (LogOps,      t("module.log")),
        "playbook": (PlaybookOps, t("module.playbook")),
    }


def print_banner() -> None:
    """Print startup banner"""
    print()
    print(f"  {bold(colorize('ClaudeSafeOps', GREEN))} — {t('banner.subtitle')}")
    print(f"  {DIM}{t('banner.tagline')}{RESET}")
    print()


def print_help() -> None:
    """Print help information"""
    print(header(t("help.title")))
    print(f"""
  {bold("connect")} <host>          {t("help.connect")}
  {bold("hosts")}                   {t("help.hosts")}
  {bold("modules")}                 {t("help.modules")}
  {bold("use")} <module>            {t("help.use")}
  {bold("run")} <command>           {t("help.run")}
  {bold("audit")} [n]               {t("help.audit")}
  {bold("risk")} <command>          {t("help.risk")}
  {bold("playbook")}                {t("help.playbook")}
  {bold("help")}                    {t("help.help")}
  {bold("exit")}                    {t("help.exit")}
""")


def print_module_help(module_name: str, ops: object) -> None:
    """Print available module methods"""
    print(header(f"Module: {module_name}"))
    methods = [
        m for m in dir(ops)
        if not m.startswith("_") and callable(getattr(ops, m))
    ]
    for m in methods:
        doc = getattr(ops, m).__doc__ or ""
        first_line = doc.strip().split("\n")[0] if doc else ""
        print(f"  {CYAN}{m:<30}{RESET} {first_line}")
    print()


def main() -> None:
    init_i18n()
    setup_logging()
    MODULE_REGISTRY = _get_module_registry()
    print_banner()

    # Initialize core components
    inventory = HostInventory()
    risk_engine = RiskEngine()
    ssh_manager = SSHConnectionManager()
    executor = CommandExecutor(
        ssh_manager=ssh_manager,
        risk_engine=risk_engine,
    )

    current_session: HostSession | None = None
    current_module_name: str | None = None
    current_ops: object | None = None

    print_help()

    if len(inventory.list_all()) == 0:
        print(warning(t("cli.no_host_config")))
        print(info(t("cli.see_example")))
        print()

    try:
        while True:
            # Build prompt
            prompt_parts = ["CsOps"]
            if current_session:
                prompt_parts.append(f"@{current_session.host}")
            if current_module_name:
                prompt_parts.append(f"/{current_module_name}")
            prompt = f"{GREEN}{''.join(prompt_parts)}{RESET}> "

            try:
                line = input(prompt).strip()
            except EOFError:
                break

            if not line:
                continue

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # ── Global commands ──────────────────────────────────
            if cmd in ("exit", "quit", "q"):
                break

            elif cmd == "help":
                if current_ops:
                    print_module_help(current_module_name, current_ops)
                else:
                    print_help()

            elif cmd == "hosts":
                hosts = inventory.list_all()
                if not hosts:
                    print(warning(t("cli.host_empty")))
                else:
                    rows = [
                        [h.hostname, h.ip, h.port, h.group, h.username, ",".join(h.tags)]
                        for h in hosts
                    ]
                    print(print_table(
                        [t("table.hostname"), t("table.ip"), t("table.port"), t("table.group"), t("table.user"), t("table.tags")],
                        rows,
                    ))
                print()

            elif cmd == "connect":
                if not args:
                    print(error(t("cli.usage_connect")))
                    continue
                host = inventory.get_host(args)
                if host:
                    ssh_config = SSHConfig(
                        host=host.ip,
                        port=host.port,
                        username=host.username,
                        auth_method=host.auth_method,
                        key_path=host.key_path,
                    )
                    print(info(t("cli.connecting", target=host.display_name)))
                else:
                    # Connect directly via IP/hostname
                    ssh_config = SSHConfig(host=args)
                    print(info(t("cli.connecting", target=args)))
                current_session = HostSession(executor, ssh_config)
                current_module_name = None
                current_ops = None
                print(success(t("cli.host_bound", host=ssh_config.host)))

            elif cmd == "modules":
                rows = [
                    [name, desc]
                    for name, (_, desc) in MODULE_REGISTRY.items()
                ]
                print(print_table([t("table.module"), t("table.description")], rows))
                print()

            elif cmd == "use":
                if not args or args not in MODULE_REGISTRY:
                    print(error(t("cli.available_modules", modules=", ".join(MODULE_REGISTRY))))
                    continue
                # playbook module doesn't require host connection (list/show/delete are local ops)
                if args == "playbook":
                    cls, desc = MODULE_REGISTRY[args]
                    current_ops = cls(current_session)  # session may be None
                elif not current_session:
                    print(error(t("cli.connect_first")))
                    continue
                else:
                    cls, desc = MODULE_REGISTRY[args]
                    current_ops = cls(current_session)
                current_module_name = args
                print(success(t("cli.switched_module", name=args, desc=desc)))
                print(info(t("cli.type_help")))

            elif cmd == "run":
                if not current_session:
                    print(error(t("cli.connect_first")))
                    continue
                if not args:
                    print(error(t("cli.usage_run")))
                    continue
                result = current_session.execute(args)
                if not result.success and result.status in ("refused", "blocked"):
                    print(warning(t("cli.cmd_not_executed", status=result.status)))

            elif cmd == "risk":
                if not args:
                    print(error(t("cli.usage_risk")))
                    continue
                level, rules = risk_engine.evaluate(args)
                print(f"  Command: {bold(args)}")
                print(f"  Risk: {risk_badge(level)}")
                if rules:
                    for r in rules:
                        print(f"    - {r.description}")
                else:
                    print(f"    {DIM}{t('cli.no_rules_default')}{RESET}")
                print()

            elif cmd == "audit":
                n = int(args) if args.isdigit() else 20
                records = executor.audit_logger.query(limit=n)
                if not records:
                    print(info(t("cli.no_audit")))
                else:
                    rows = [
                        [r["timestamp"][:19], r["host"], r["command"][:40],
                         r["risk_level"], r["status"]]
                        for r in records
                    ]
                    print(print_table(
                        [t("table.time"), t("table.host"), t("table.command"), t("table.risk"), t("table.status")],
                        rows,
                    ))
                print()

            elif cmd == "playbook":
                # Shortcut: equivalent to "use playbook"
                cls, desc = MODULE_REGISTRY["playbook"]
                current_ops = cls(current_session)
                current_module_name = "playbook"
                print(success(t("cli.switched_module", name="playbook", desc=desc)))
                print(info(t("cli.type_help")))

            # ── Module method dispatch ──────────────────────────────
            elif current_ops and hasattr(current_ops, cmd):
                method = getattr(current_ops, cmd)
                if callable(method):
                    try:
                        # Simple arg parsing: split by spaces
                        call_args = args.split() if args else []
                        result = method(*call_args)
                        if result and hasattr(result, "output") and result.output:
                            print(result.output)
                    except TypeError as e:
                        print(error(t("cli.arg_error", error=e)))
                    except Exception as e:
                        print(error(t("cli.exec_error", error=e)))
                print()

            else:
                print(error(t("cli.unknown_cmd", cmd=cmd)))
                print(info(t("cli.type_help_short")))

    except KeyboardInterrupt:
        print()

    finally:
        ssh_manager.close_all()
        print(info(t("cli.goodbye")))


if __name__ == "__main__":
    main()
