"""Security operations module providing port scanning, login auditing, SSH config checks, permission reviews, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult


class SecurityOps:
    """Security operations collection covering port auditing, login analysis, permission checks, and other routine security inspection tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize security operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Port Auditing
    # ------------------------------------------------------------------

    def check_open_ports(self) -> CommandResult:
        """Check all TCP listening ports and associated processes."""
        return self._exec.execute("ss -tlnp")

    # ------------------------------------------------------------------
    # Login and Authentication Auditing
    # ------------------------------------------------------------------

    def check_failed_logins(self) -> CommandResult:
        """Check SSH failed login records (extracted from auth.log or secure log)."""
        cmd = (
            "grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -50 || "
            "grep 'Failed password' /var/log/secure 2>/dev/null | tail -50 || "
            "journalctl -u sshd --no-pager 2>/dev/null | grep 'Failed password' | tail -50 || "
            "echo 'No failed login records found'"
        )
        return self._exec.execute(cmd)

    def check_sudo_log(self) -> CommandResult:
        """Check sudo usage records."""
        cmd = (
            "grep 'sudo' /var/log/auth.log 2>/dev/null | tail -50 || "
            "grep 'sudo' /var/log/secure 2>/dev/null | tail -50 || "
            "journalctl -t sudo --no-pager -n 50 2>/dev/null || "
            "echo 'No sudo log records found'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # File Permissions
    # ------------------------------------------------------------------

    def check_file_permissions(self, path: str) -> CommandResult:
        """Check file permission details for the specified path and scan for SUID/SGID files.

        Args:
            path: File or directory path to check.
        """
        cmd = (
            f"echo '=== stat ===' && stat {path} && "
            f"echo '=== SUID files ===' && "
            f"find {path} -perm -4000 -type f 2>/dev/null | head -20 && "
            f"echo '=== SGID files ===' && "
            f"find {path} -perm -2000 -type f 2>/dev/null | head -20"
        )
        return self._exec.execute(cmd, timeout=60)

    # ------------------------------------------------------------------
    # SSH Configuration
    # ------------------------------------------------------------------

    def check_ssh_config(self) -> CommandResult:
        """Check key SSH server security configuration settings."""
        cmd = (
            "echo '=== sshd_config key settings ===' && "
            "grep -E '^\\s*(PermitRootLogin|PasswordAuthentication|"
            "PubkeyAuthentication|Port|MaxAuthTries|"
            "AllowUsers|AllowGroups|Protocol|X11Forwarding|"
            "PermitEmptyPasswords)' /etc/ssh/sshd_config 2>/dev/null || "
            "echo 'Cannot read /etc/ssh/sshd_config'"
        )
        return self._exec.execute(cmd)

    def list_authorized_keys(self) -> CommandResult:
        """List SSH authorized public keys for the current user and root."""
        cmd = (
            "echo '=== current user ===' && "
            "cat ~/.ssh/authorized_keys 2>/dev/null || echo 'No authorized_keys' && "
            "echo '=== root ===' && "
            "cat /root/.ssh/authorized_keys 2>/dev/null || echo 'No root authorized_keys or no permission'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # Process Security
    # ------------------------------------------------------------------

    def check_running_as_root(self) -> CommandResult:
        """Find processes running as root."""
        return self._exec.execute(
            "ps aux | awk '$1==\"root\"' | head -50"
        )

    # ------------------------------------------------------------------
    # System Updates
    # ------------------------------------------------------------------

    def check_updates(self) -> CommandResult:
        """Check for available system updates (auto-detects package manager)."""
        cmd = (
            "if command -v apt &>/dev/null; then "
            "  apt list --upgradable 2>/dev/null; "
            "elif command -v yum &>/dev/null; then "
            "  yum check-update 2>/dev/null; "
            "elif command -v dnf &>/dev/null; then "
            "  dnf check-update 2>/dev/null; "
            "else "
            "  echo 'No supported package manager found (apt/yum/dnf)'; "
            "fi"
        )
        return self._exec.execute(cmd, timeout=60)

    # ------------------------------------------------------------------
    # Password Policy
    # ------------------------------------------------------------------

    def check_password_policy(self) -> CommandResult:
        """Check system password policy configuration."""
        cmd = (
            "echo '=== /etc/login.defs key fields ===' && "
            "grep -E '^(PASS_MAX_DAYS|PASS_MIN_DAYS|PASS_MIN_LEN|PASS_WARN_AGE|"
            "LOGIN_RETRIES|LOGIN_TIMEOUT)' /etc/login.defs 2>/dev/null || "
            "echo 'Cannot read /etc/login.defs'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # SUID File Scanning
    # ------------------------------------------------------------------

    def scan_large_suid_files(self) -> CommandResult:
        """Scan the entire filesystem for SUID files (useful for detecting potential privilege escalation risks)."""
        cmd = (
            "find / -perm -4000 -type f 2>/dev/null | "
            "xargs ls -lh 2>/dev/null | "
            "sort -k5 -rh | head -30"
        )
        return self._exec.execute(cmd, timeout=120)
