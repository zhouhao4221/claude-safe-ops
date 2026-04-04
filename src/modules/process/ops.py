"""Process operations module providing process queries, resource sorting, process tree, signal sending, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult, RiskLevel


class ProcessOps:
    """Process operations collection covering process listing, resource usage sorting, process management, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize process operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Process Queries
    # ------------------------------------------------------------------

    def list_processes(self) -> CommandResult:
        """List all processes sorted by memory usage in descending order."""
        return self._exec.execute("ps aux --sort=-%mem")

    def get_top_cpu(self, n: int = 10) -> CommandResult:
        """Get the top N processes by CPU usage.

        Args:
            n: Number of processes to return, default 10.
        """
        return self._exec.execute(f"ps aux --sort=-%cpu | head -n {n + 1}")

    def get_top_memory(self, n: int = 10) -> CommandResult:
        """Get the top N processes by memory usage.

        Args:
            n: Number of processes to return, default 10.
        """
        return self._exec.execute(f"ps aux --sort=-%mem | head -n {n + 1}")

    def find_process(self, name: str) -> CommandResult:
        """Search for processes by name.

        Args:
            name: Process name or keyword to search for.
        """
        return self._exec.execute(f"ps aux | grep '[{name[0]}]{name[1:]}'" if len(name) > 1
                                   else f"ps aux | grep '[{name}]'")

    def get_process_tree(self) -> CommandResult:
        """Get the process tree (including PIDs)."""
        return self._exec.execute("pstree -p 2>/dev/null || ps axjf")

    # ------------------------------------------------------------------
    # Process Management
    # ------------------------------------------------------------------

    def kill_process(self, pid: int, signal: int = 15) -> CommandResult:
        """Send a signal to a specific process. Risk level is HIGH when using kill -9.

        Args:
            pid: Target process PID.
            signal: Signal number, default 15 (SIGTERM). Common values: 9 (SIGKILL), 15 (SIGTERM).
        """
        risk = RiskLevel.HIGH if signal == 9 else RiskLevel.MEDIUM
        _ = risk  # Left for upstream call chain to perform risk validation
        return self._exec.execute(f"kill -{signal} {pid}")

    # ------------------------------------------------------------------
    # Process Details
    # ------------------------------------------------------------------

    def get_open_files(self, pid: int) -> CommandResult:
        """Get the list of files opened by a specific process.

        Args:
            pid: Target process PID.
        """
        return self._exec.execute(f"lsof -p {pid} 2>/dev/null || ls -l /proc/{pid}/fd 2>/dev/null")

    # ------------------------------------------------------------------
    # System Resource Overview
    # ------------------------------------------------------------------

    def get_system_resources(self) -> CommandResult:
        """Get system resource sampling (vmstat continuous sampling 5 times, 1 second interval)."""
        return self._exec.execute("vmstat 1 5", timeout=15)
