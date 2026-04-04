"""Deployment operations module providing app status checks, file deployment, backup rollback, health checks, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult


class DeployOps:
    """Deployment operations collection covering app deployment, version management, health checks, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize deployment operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Application Status
    # ------------------------------------------------------------------

    def check_app_status(self, app_name: str) -> CommandResult:
        """Check application running status, querying systemd service first, then Docker container.

        Args:
            app_name: Application/service name.
        """
        cmd = (
            f"systemctl is-active {app_name} 2>/dev/null && "
            f"systemctl status {app_name} --no-pager 2>/dev/null || "
            f"docker ps --filter name={app_name} --format "
            f"'table {{{{.ID}}}}\\t{{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}' 2>/dev/null || "
            f"echo 'Service {app_name} not found in systemd or docker'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # File Deployment
    # ------------------------------------------------------------------

    def deploy_files(self, local_path: str, remote_path: str) -> CommandResult:
        """Upload local files to a remote target path (via SFTP).

        Args:
            local_path: Local file or directory path.
            remote_path: Remote target path.
        """
        return self._exec.upload(local_path, remote_path)

    def backup_before_deploy(self, path: str) -> CommandResult:
        """Create a timestamped backup of the target path before deployment.

        Args:
            path: Remote directory/file path to back up.
        """
        cmd = (
            f"timestamp=$(date +%Y%m%d_%H%M%S) && "
            f"cp -a {path} {path}.bak_${{timestamp}} && "
            f"echo 'Backup created: {path}.bak_'${{timestamp}}"
        )
        return self._exec.execute(cmd)

    def rollback(self, path: str, backup_path: str) -> CommandResult:
        """Restore application files from a backup (rollback deployment).

        Args:
            path: Current application path (will be overwritten).
            backup_path: Backup file/directory path.
        """
        cmd = (
            f"if [ -e {backup_path} ]; then "
            f"  rm -rf {path} && cp -a {backup_path} {path} && "
            f"  echo 'Rollback completed: {backup_path} -> {path}'; "
            f"else "
            f"  echo 'ERROR: backup not found: {backup_path}'; "
            f"fi"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # Application Management
    # ------------------------------------------------------------------

    def restart_app(self, app_name: str) -> CommandResult:
        """Restart an application, trying systemd first, then Docker.

        Args:
            app_name: Application/service name.
        """
        cmd = (
            f"systemctl restart {app_name} 2>/dev/null && "
            f"echo 'Restarted via systemd' || "
            f"(docker restart {app_name} 2>/dev/null && "
            f"echo 'Restarted via docker') || "
            f"echo 'Failed to restart {app_name}'"
        )
        return self._exec.execute(cmd)

    def get_app_version(self, path: str) -> CommandResult:
        """Get application version info, trying VERSION file, package.json, and git log in order.

        Args:
            path: Application root directory path.
        """
        cmd = (
            f"if [ -f {path}/VERSION ]; then "
            f"  echo 'VERSION file:' && cat {path}/VERSION; "
            f"elif [ -f {path}/version.txt ]; then "
            f"  echo 'version.txt:' && cat {path}/version.txt; "
            f"elif [ -f {path}/package.json ]; then "
            f"  echo 'package.json version:' && "
            f"  grep '\"version\"' {path}/package.json; "
            f"elif [ -d {path}/.git ]; then "
            f"  echo 'git log:' && "
            f"  git -C {path} log --oneline -5; "
            f"else "
            f"  echo 'No version info found in {path}'; "
            f"fi"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # Health Checks
    # ------------------------------------------------------------------

    def check_health(self, url: str) -> CommandResult:
        """Check application health endpoint via HTTP request.

        Args:
            url: Health check URL, e.g. ``http://localhost:8080/health``.
        """
        cmd = (
            f"curl -sf -o /dev/null -w "
            f"'HTTP_CODE=%{{http_code}} TIME=%{{time_total}}s' "
            f"'{url}' && echo ' OK' || echo ' FAILED'"
        )
        return self._exec.execute(cmd, timeout=15)

    def tail_app_log(self, app_name: str, lines: int = 100) -> CommandResult:
        """View recent log output for an application.

        Args:
            app_name: Application/service name.
            lines: Number of log lines to return, default 100.
        """
        cmd = (
            f"journalctl -u {app_name} -n {lines} --no-pager 2>/dev/null || "
            f"docker logs --tail {lines} {app_name} 2>/dev/null || "
            f"echo 'No logs found for {app_name}'"
        )
        return self._exec.execute(cmd)
