"""System operations module providing system info queries, service management, user management, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult, RiskLevel


# Stopping these critical services is marked as HIGH risk
_CRITICAL_SERVICES = frozenset({
    "sshd", "ssh", "networking", "network", "NetworkManager",
    "systemd-journald", "systemd-logind", "dbus", "firewalld",
    "iptables", "crond", "cron", "rsyslog", "auditd",
})


class SystemOps:
    """System operations collection covering system info gathering, service management, user queries, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize system operations.

        Args:
            session: Host session instance for executing commands on the target host.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # System Information
    # ------------------------------------------------------------------

    def get_system_info(self) -> CommandResult:
        """Get basic system info including kernel version, hostname, OS distribution, and uptime."""
        cmd = (
            "echo '=== uname ===' && uname -a && "
            "echo '=== os-release ===' && cat /etc/os-release 2>/dev/null && "
            "echo '=== hostname ===' && hostname && "
            "echo '=== uptime ===' && uptime"
        )
        return self._exec.execute(cmd)

    def get_cpu_info(self) -> CommandResult:
        """Get CPU info summary including architecture, core count, model, etc."""
        cmd = (
            "echo '=== lscpu ===' && lscpu 2>/dev/null && "
            "echo '=== cpuinfo summary ===' && "
            "grep -m1 'model name' /proc/cpuinfo 2>/dev/null && "
            "grep -c '^processor' /proc/cpuinfo 2>/dev/null"
        )
        return self._exec.execute(cmd)

    def get_memory_info(self) -> CommandResult:
        """Get memory usage in human-readable format."""
        return self._exec.execute("free -h")

    def get_load_average(self) -> CommandResult:
        """Get system load averages (1/5/15 minutes)."""
        cmd = (
            "uptime && "
            "cat /proc/loadavg 2>/dev/null"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # Service Management
    # ------------------------------------------------------------------

    def list_services(self) -> CommandResult:
        """List all systemd service units and their statuses."""
        return self._exec.execute("systemctl list-units --type=service --no-pager")

    def service_status(self, name: str) -> CommandResult:
        """Query the running status of a specific service.

        Args:
            name: Service name, e.g. ``nginx`` or ``sshd``.
        """
        return self._exec.execute(f"systemctl status {name} --no-pager")

    def restart_service(self, name: str) -> CommandResult:
        """Restart a specific service. Risk level: MEDIUM.

        Args:
            name: Service name.
        """
        # Risk level: MEDIUM - restarting a service causes brief unavailability
        return self._exec.execute(f"systemctl restart {name}")

    def stop_service(self, name: str) -> CommandResult:
        """Stop a specific service. Risk level is HIGH for critical services (e.g. sshd).

        Args:
            name: Service name.
        """
        risk = RiskLevel.HIGH if name in _CRITICAL_SERVICES else RiskLevel.MEDIUM
        _ = risk  # Left for upstream call chain to perform risk validation
        return self._exec.execute(f"systemctl stop {name}")

    # ------------------------------------------------------------------
    # Users and Logins
    # ------------------------------------------------------------------

    def list_users(self) -> CommandResult:
        """Parse /etc/passwd to list system users (username, UID, GID, home directory, shell)."""
        cmd = (
            "awk -F: '{printf \"%-20s UID=%-6s GID=%-6s HOME=%-25s SHELL=%s\\n\", "
            "$1, $3, $4, $6, $7}' /etc/passwd"
        )
        return self._exec.execute(cmd)

    def check_last_logins(self) -> CommandResult:
        """View the last 20 login records."""
        return self._exec.execute("last -n 20")

    def get_crontab(self) -> CommandResult:
        """Get the current user's crontab scheduled task list."""
        return self._exec.execute("crontab -l 2>/dev/null || echo 'no crontab for current user'")
