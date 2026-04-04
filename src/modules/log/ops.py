"""Log operations module providing log viewing, searching, system logs, log rotation checks, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult


class LogOps:
    """Log operations collection covering log viewing, keyword searching, error summarization, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize log operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Log Viewing
    # ------------------------------------------------------------------

    def tail_log(self, path: str, lines: int = 100) -> CommandResult:
        """View the last N lines of a log file.

        Args:
            path: Log file path.
            lines: Number of lines to return, default 100.
        """
        return self._exec.execute(f"tail -n {lines} {path}")

    def follow_log(self, path: str, lines: int = 50) -> CommandResult:
        """Get the latest content of a log file (non-interactive mode, equivalent to tail -n).

        Note: True ``tail -f`` streaming is not possible in a non-interactive
        environment; this method returns the last N lines as an alternative.

        Args:
            path: Log file path.
            lines: Number of lines to return, default 50.
        """
        return self._exec.execute(f"tail -n {lines} {path}")

    # ------------------------------------------------------------------
    # Log Searching
    # ------------------------------------------------------------------

    def search_log(self, path: str, keyword: str) -> CommandResult:
        """Search for lines containing a specified keyword in a log file.

        Args:
            path: Log file path.
            keyword: Search keyword.
        """
        return self._exec.execute(f"grep -n '{keyword}' {path} | tail -100")

    def get_error_summary(self, path: str) -> CommandResult:
        """Count occurrences of ERROR, WARN, and FATAL keywords in a log file.

        Args:
            path: Log file path.
        """
        cmd = (
            f"echo '=== Error Summary for {path} ===' && "
            f"echo -n 'ERROR:  ' && grep -ci 'error' {path} 2>/dev/null || echo '0' && "
            f"echo -n 'WARN:   ' && grep -ci 'warn' {path} 2>/dev/null || echo '0' && "
            f"echo -n 'FATAL:  ' && grep -ci 'fatal' {path} 2>/dev/null || echo '0'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # System Logs
    # ------------------------------------------------------------------

    def get_syslog(self, lines: int = 100) -> CommandResult:
        """Get system logs (via journalctl).

        Args:
            lines: Number of lines to return, default 100.
        """
        return self._exec.execute(f"journalctl -n {lines} --no-pager")

    def get_kernel_log(self, lines: int = 50) -> CommandResult:
        """Get kernel logs (dmesg).

        Args:
            lines: Number of lines to return, default 50.
        """
        return self._exec.execute(f"dmesg | tail -n {lines}")

    # ------------------------------------------------------------------
    # Log File Management
    # ------------------------------------------------------------------

    def get_log_size(self, path: str = "/var/log") -> CommandResult:
        """Get the disk usage of a log file or directory.

        Args:
            path: Log path, defaults to ``/var/log``.
        """
        cmd = (
            f"du -sh {path} 2>/dev/null && "
            f"echo '=== Top 10 largest log files ===' && "
            f"find {path} -type f -name '*.log' -o -name '*.gz' 2>/dev/null | "
            f"xargs du -sh 2>/dev/null | sort -rh | head -10"
        )
        return self._exec.execute(cmd)

    def check_log_rotation(self) -> CommandResult:
        """Check logrotate configuration."""
        cmd = (
            "echo '=== /etc/logrotate.conf ===' && "
            "cat /etc/logrotate.conf 2>/dev/null || echo 'Not found' && "
            "echo '=== /etc/logrotate.d/ ===' && "
            "ls -la /etc/logrotate.d/ 2>/dev/null || echo 'Not found'"
        )
        return self._exec.execute(cmd)
