"""
Playbook operations module

Provides playbook viewing, execution, saving, and deletion operations.
list/show/delete do not require a host connection; run/save require an active HostSession.
"""

from __future__ import annotations

from typing import Optional

from src.executor import HostSession, CommandResult
from src.executor.command_executor import AuditLogger
from src.modules.playbook.manager import PlaybookManager, Playbook, PlaybookStep
from src.utils.i18n import t
from src.utils.output import (
    bold, colorize, confirm_prompt, header, info, separator,
    success, warning, error, print_table, print_kv, dim,
    GREEN, CYAN, YELLOW, RED, DIM, RESET, MAGENTA,
)


class PlaybookOps:
    """
    Playbook operations collection

    Special note: session can be None (list/show/delete do not require a host connection).
    """

    def __init__(self, session: Optional[HostSession] = None) -> None:
        self._exec = session
        self._manager = PlaybookManager()

    def list(self, tag: str = "") -> None:
        """List all available playbooks, optionally filtered by tag. Usage: list [tag]"""
        playbooks = self._manager.list_all(tag=tag or None)

        if not playbooks:
            if tag:
                print(info(t("playbook.no_tag", tag=tag)))
            else:
                print(info(t("playbook.none_available")))
            return

        rows = []
        for pb in playbooks:
            source_badge = f"{DIM}{t('playbook.source_builtin')}{RESET}" if pb.source == "builtin" else f"{GREEN}{t('playbook.source_user')}{RESET}"
            tags_str = ", ".join(pb.tags) if pb.tags else "-"
            rows.append([pb.name, pb.description[:40], tags_str, source_badge])

        print(print_table(
            [t("table.name"), t("table.description"), t("table.tags"), t("table.source")],
            rows,
        ))
        print()

    def show(self, name: str = "") -> None:
        """Show playbook details. Usage: show <name>"""
        if not name:
            print(error(t("playbook.usage_show")))
            return

        pb = self._manager.get(name)
        if not pb:
            print(error(t("playbook.not_found", name=name)))
            return

        source_label = t("playbook.source_builtin") if pb.source == "builtin" else t("playbook.source_user")
        print(header(f"Playbook: {pb.name}"))
        print(print_kv({
            t("table.description"): pb.description,
            t("table.tags"): ", ".join(pb.tags) if pb.tags else "-",
            t("table.source"): source_label,
            t("playbook.path"): str(pb.path),
        }))

        if pb.vars:
            print()
            print(f"  {bold(t('playbook.variables'))}:")
            for k, v in pb.vars.items():
                print(f"    {CYAN}{k}{RESET} = {v}")

        print()
        print(f"  {bold(t('playbook.steps'))}:")
        for i, step in enumerate(pb.steps, 1):
            fail_tag = f" {DIM}[{t('playbook.continue_on_fail')}]{RESET}" if step.on_fail == "continue" else ""
            print(f"    {YELLOW}{i}.{RESET} {step.name}{fail_tag}")
            print(f"       {DIM}${RESET} {step.command}")

        if pb.notes:
            print()
            print(f"  {bold(t('playbook.notes'))}:")
            for line in pb.notes.strip().splitlines():
                print(f"    {line}")

        print()

    def run(self, *args: str) -> None:
        """Run a playbook. Usage: run <name> [var1=value1 var2=value2 ...]"""
        if not args:
            print(error(t("playbook.usage_run")))
            return

        if not self._exec:
            print(error(t("cli.connect_first")))
            return

        name = args[0]
        pb = self._manager.get(name)
        if not pb:
            print(error(t("playbook.not_found", name=name)))
            return

        # Parse variable overrides: key=value
        var_overrides: dict[str, str] = {}
        for arg in args[1:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                var_overrides[k] = v

        # Merge variables: defaults + overrides
        variables = {**pb.vars, **var_overrides}

        # Check for unassigned variables
        used_vars = self._manager.extract_vars(pb)
        missing = used_vars - set(variables.keys())
        if missing:
            print(error(t("playbook.missing_vars", vars=", ".join(sorted(missing)))))
            print(info(t("playbook.missing_vars_hint", name=name, usage=" ".join(f"{v}=<value>" for v in sorted(missing)))))
            return

        # Display execution plan
        print(header(f"Run Playbook: {pb.name}"))
        print(f"  {bold(t('playbook.target_host'))}: {self._exec.host}")
        if variables:
            print(f"  {bold(t('playbook.variables'))}:")
            for k, v in variables.items():
                print(f"    {k} = {v}")
        print()
        print(f"  {bold(t('playbook.exec_steps'))}:")
        for i, step in enumerate(pb.steps, 1):
            rendered = self._manager.render_command(step.command, variables)
            print(f"    {i}. {step.name}")
            print(f"       $ {rendered}")
        print()

        if not confirm_prompt(t("playbook.confirm_run", host=self._exec.host)):
            print(info(t("playbook.cancelled")))
            return

        # Execute steps one by one
        print()
        results: list[tuple[PlaybookStep, str, bool]] = []  # (step, status, success)

        for i, step in enumerate(pb.steps, 1):
            rendered_cmd = self._manager.render_command(step.command, variables)
            print(f"{CYAN}[{i}/{len(pb.steps)}]{RESET} {bold(step.name)}")
            print(f"  $ {rendered_cmd}")

            result = self._exec.execute(rendered_cmd)

            if result.success:
                results.append((step, "Success", True))
                print(success(t("playbook.step_done")))
            else:
                if step.on_fail == "continue":
                    results.append((step, "Failed(continued)", False))
                    print(warning(t("playbook.step_failed_cont", code=result.exit_code)))
                else:
                    results.append((step, "Failed(aborted)", False))
                    print(error(t("playbook.step_failed_abort", code=result.exit_code)))
                    break
            print()

        # Execution summary
        print(header(t("playbook.summary_title")))
        total = len(results)
        ok_count = sum(1 for _, _, s in results if s)
        fail_count = total - ok_count
        skipped = len(pb.steps) - total

        rows = []
        for step, status, s in results:
            status_colored = f"{GREEN}{status}{RESET}" if s else f"{RED}{status}{RESET}"
            rows.append([step.name, status_colored])
        if skipped > 0:
            rows.append([t("playbook.steps_skipped", n=skipped), f"{DIM}{t('playbook.not_executed')}{RESET}"])

        print(print_table([t("table.step"), t("table.status")], rows))
        print()

        if fail_count == 0 and skipped == 0:
            print(success(t("playbook.all_succeeded", ok=ok_count, total=len(pb.steps))))
        else:
            print(warning(t("playbook.partial", ok=ok_count, fail=fail_count, skip=skipped)))
        print()

    def save(self, name: str = "") -> None:
        """Create a playbook from recent operations. Usage: save <name>"""
        if not name:
            print(error(t("playbook.usage_save")))
            return

        # Check if already exists
        existing = self._manager.get(name)
        if existing and existing.source == "builtin":
            print(warning(t("playbook.builtin_override", name=name)))
        elif existing and existing.source == "user":
            if not confirm_prompt(t("playbook.confirm_overwrite", name=name)):
                print(info(t("playbook.cancelled")))
                return

        # Get recent commands from audit log
        audit = AuditLogger()
        host_filter = self._exec.host if self._exec else None
        records = audit.query(host=host_filter, limit=30)
        executed = [
            r for r in records
            if r.get("status") in ("executed", "confirmed")
        ]

        if not executed:
            print(info(t("playbook.no_history")))
            print(info(t("playbook.save_tip")))
            return

        # Display recent commands for selection
        print(header(t("playbook.recent_title")))
        for i, rec in enumerate(executed[-15:], 1):
            ts = rec.get("timestamp", "")[:19]
            cmd = rec.get("command", "")[:60]
            host = rec.get("host", "")
            print(f"  {YELLOW}{i:>3}{RESET}. [{ts}] {host}: {cmd}")
        print()

        # Interactive selection
        try:
            selection = input(f"{CYAN}{t('playbook.select_cmds')}{RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(info(t("playbook.cancelled")))
            return

        if not selection:
            print(info(t("playbook.no_selection")))
            return

        indices: list[int] = []
        display_records = executed[-15:]
        for s in selection.split(","):
            s = s.strip()
            if s.isdigit():
                idx = int(s) - 1
                if 0 <= idx < len(display_records):
                    indices.append(idx)

        if not indices:
            print(error(t("playbook.invalid_selection")))
            return

        selected_cmds = [display_records[i]["command"] for i in indices]

        # Input description and tags
        try:
            description = input(f"{CYAN}{t('playbook.desc_prompt')}{RESET}").strip() or name
            tags_input = input(f"{CYAN}{t('playbook.tags_prompt')}{RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(info(t("playbook.cancelled")))
            return

        tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []

        # Build steps
        steps: list[PlaybookStep] = []
        for i, cmd in enumerate(selected_cmds, 1):
            step_name = f"Step {i}"
            steps.append(PlaybookStep(name=step_name, command=cmd))

        playbook = Playbook(
            name=name,
            description=description,
            tags=tags,
            steps=steps,
        )

        path = self._manager.save(playbook)
        print()
        print(success(t("playbook.saved", path=path)))
        print(info(t("playbook.save_edit_tip")))
        print()

    def delete(self, name: str = "") -> None:
        """Delete a user playbook. Usage: delete <name>"""
        if not name:
            print(error(t("playbook.usage_delete")))
            return

        pb = self._manager.get(name)
        if not pb:
            print(error(t("playbook.not_found", name=name)))
            return

        if pb.source == "builtin":
            print(error(t("playbook.cannot_delete_builtin")))
            return

        if not confirm_prompt(t("playbook.confirm_delete", name=name)):
            print(info(t("playbook.cancelled")))
            return

        if self._manager.delete(name):
            print(success(t("playbook.deleted", name=name)))
        else:
            print(error(t("playbook.delete_failed")))
