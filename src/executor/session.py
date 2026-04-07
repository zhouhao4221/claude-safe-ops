"""
Host session

Binds a CommandExecutor to a specific host, providing a simplified execution interface.
Operations modules (modules/*) execute commands via HostSession without knowing SSH config details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.connection.ssh_client import SSHConfig
from src.executor.command_executor import CommandExecutor, CommandRecord
from src.utils.i18n import t


@dataclass
class CommandResult:
    """Command execution result (simplified view for ops modules)"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    risk_level: str
    status: str  # executed | confirmed | blocked | refused | error

    @property
    def output(self) -> str:
        """Get stdout (trailing whitespace stripped)"""
        return self.stdout.rstrip()

    def __bool__(self) -> bool:
        return self.success


class HostSession:
    """
    Host session — command executor bound to a specific host

    Ops modules execute commands through this class with a simple interface:
        session = HostSession(executor, ssh_config)
        result = session.execute("df -h")

    All commands are automatically assessed by the risk engine.
    """

    def __init__(self, executor: CommandExecutor, ssh_config: SSHConfig) -> None:
        self._executor = executor
        self._ssh_config = ssh_config
        # Populated lazily by ``load_metadata`` so tests and offline uses don't
        # pay the cost of probing a remote host on construction.
        self._metadata = None  # type: ignore[assignment]

    @property
    def metadata(self):
        """Cached host metadata (HostMetadata | None). Call load_metadata() first."""
        return self._metadata

    def load_metadata(self, *, force: bool = False):
        """Load or refresh the host metadata cache. Returns HostMetadata or None on failure."""
        try:
            from src.utils.host_cache import HostMetadataCache
            self._metadata = HostMetadataCache().get_or_fetch(self, force=force)
        except Exception:  # noqa: BLE001
            self._metadata = None
        return self._metadata

    @property
    def host(self) -> str:
        return self._ssh_config.host

    def execute(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """
        Execute a command on the bound host

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds, None for default

        Returns:
            CommandResult simplified execution result
        """
        record: CommandRecord = self._executor.execute(self._ssh_config, command)

        return CommandResult(
            success=(record.exit_code == 0 and record.status in ("executed", "confirmed")),
            stdout=record.stdout,
            stderr=record.stderr,
            exit_code=record.exit_code,
            risk_level=record.risk_level,
            status=record.status,
        )

    def upload(self, local_path: str, remote_path: str) -> CommandResult:
        """Upload a file to the remote host"""
        try:
            self._executor._ssh.upload_file(self._ssh_config, local_path, remote_path)
            return CommandResult(
                success=True,
                stdout=t("session.uploaded", local=local_path, host=self.host, remote=remote_path),
                stderr="",
                exit_code=0,
                risk_level="MEDIUM",
                status="executed",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=1,
                risk_level="MEDIUM",
                status="error",
            )

    def download(self, remote_path: str, local_path: str) -> CommandResult:
        """Download a file from the remote host"""
        try:
            self._executor._ssh.download_file(self._ssh_config, remote_path, local_path)
            return CommandResult(
                success=True,
                stdout=t("session.downloaded", host=self.host, remote=remote_path, local=local_path),
                stderr="",
                exit_code=0,
                risk_level="LOW",
                status="executed",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=1,
                risk_level="LOW",
                status="error",
            )
