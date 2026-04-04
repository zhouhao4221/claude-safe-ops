"""Backup operations module providing directory backup, database backup, backup restoration, cleanup, and more."""

from __future__ import annotations

from src.executor import HostSession, CommandResult, RiskLevel


class BackupOps:
    """Backup operations collection covering file backup, database export, backup management, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize backup operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Directory Backup
    # ------------------------------------------------------------------

    def backup_directory(self, path: str, dest: str) -> CommandResult:
        """Compress and back up a directory to the target path (tar.gz format, filename includes timestamp).

        Args:
            path: Source directory to back up.
            dest: Directory to store the backup file.
        """
        cmd = (
            f"timestamp=$(date +%Y%m%d_%H%M%S) && "
            f"dirname=$(basename {path}) && "
            f"mkdir -p {dest} && "
            f"tar czf {dest}/${{dirname}}_${{timestamp}}.tar.gz -C $(dirname {path}) ${{dirname}} && "
            f"echo 'Backup created: {dest}/'${{dirname}}'_'${{timestamp}}'.tar.gz'"
        )
        return self._exec.execute(cmd, timeout=300)

    # ------------------------------------------------------------------
    # Database Backup
    # ------------------------------------------------------------------

    def backup_database(self, db_type: str, db_name: str, dest: str) -> CommandResult:
        """Export a database backup. Supports MySQL and PostgreSQL.

        Args:
            db_type: Database type, valid values are ``mysql`` or ``postgresql``.
            db_name: Database name.
            dest: Directory to store the backup file.
        """
        timestamp_expr = "$(date +%Y%m%d_%H%M%S)"
        if db_type.lower() in ("mysql", "mariadb"):
            cmd = (
                f"mkdir -p {dest} && "
                f"mysqldump {db_name} | gzip > "
                f"{dest}/{db_name}_{timestamp_expr}.sql.gz && "
                f"echo 'MySQL backup completed'"
            )
        elif db_type.lower() in ("postgresql", "postgres", "pg"):
            cmd = (
                f"mkdir -p {dest} && "
                f"pg_dump {db_name} | gzip > "
                f"{dest}/{db_name}_{timestamp_expr}.sql.gz && "
                f"echo 'PostgreSQL backup completed'"
            )
        else:
            cmd = f"echo 'Unsupported database type: {db_type}. Supported: mysql, postgresql'"
        return self._exec.execute(cmd, timeout=600)

    # ------------------------------------------------------------------
    # Backup Management
    # ------------------------------------------------------------------

    def list_backups(self, path: str) -> CommandResult:
        """List files in the backup directory (sorted by time, newest first).

        Args:
            path: Backup storage directory.
        """
        return self._exec.execute(f"ls -lht {path} 2>/dev/null || echo 'Directory not found: {path}'")

    def get_backup_size(self, path: str) -> CommandResult:
        """Get the size of a backup file or directory.

        Args:
            path: Backup file or directory path.
        """
        return self._exec.execute(f"du -sh {path} 2>/dev/null || echo 'Path not found: {path}'")

    def verify_backup(self, backup_file: str) -> CommandResult:
        """Verify the integrity of a tar.gz backup file (list contents without extracting).

        Args:
            backup_file: Backup file path (.tar.gz).
        """
        return self._exec.execute(
            f"tar tzf {backup_file} > /dev/null 2>&1 && "
            f"echo 'Backup integrity OK: {backup_file}' && "
            f"echo 'Contents:' && tar tzf {backup_file} | head -20 || "
            f"echo 'ERROR: Backup file is corrupted or not a valid tar.gz'"
        )

    # ------------------------------------------------------------------
    # Backup Restoration (High Risk)
    # ------------------------------------------------------------------

    def restore_backup(self, backup_file: str, dest: str) -> CommandResult:
        """Restore from a tar.gz backup to the target path. Risk level: HIGH.

        Args:
            backup_file: Backup file path.
            dest: Restore target directory.
        """
        # Risk level: HIGH - restore operation overwrites the target directory
        _ = RiskLevel.HIGH
        cmd = (
            f"mkdir -p {dest} && "
            f"tar xzf {backup_file} -C {dest} && "
            f"echo 'Restore completed: {backup_file} -> {dest}'"
        )
        return self._exec.execute(cmd, timeout=300)

    # ------------------------------------------------------------------
    # Scheduled Backup
    # ------------------------------------------------------------------

    def schedule_backup(self, cron_expr: str, command: str) -> CommandResult:
        """Add a backup command to crontab scheduled tasks. Risk level: MEDIUM.

        Args:
            cron_expr: Cron expression, e.g. ``0 2 * * *`` (daily at 2 AM).
            command: Backup command to schedule.
        """
        # Risk level: MEDIUM - modifies crontab
        _ = RiskLevel.MEDIUM
        cmd = (
            f"(crontab -l 2>/dev/null; echo '{cron_expr} {command}') | "
            f"crontab - && echo 'Cron job added successfully' && crontab -l"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # Old Backup Cleanup (High Risk)
    # ------------------------------------------------------------------

    def cleanup_old_backups(self, path: str, keep_days: int = 30) -> CommandResult:
        """Clean up backup files older than the retention period in the specified directory. Risk level: HIGH.

        Args:
            path: Backup file directory.
            keep_days: Retention period in days, default 30.
        """
        # Risk level: HIGH - deleted files cannot be recovered
        _ = RiskLevel.HIGH
        cmd = (
            f"echo 'Files to delete (older than {keep_days} days):' && "
            f"find {path} -type f -mtime +{keep_days} -ls && "
            f"find {path} -type f -mtime +{keep_days} -delete && "
            f"echo 'Cleanup completed'"
        )
        return self._exec.execute(cmd, timeout=120)
