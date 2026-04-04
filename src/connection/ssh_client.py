"""
SSH connection manager

SSH connection pool, command execution, and file transfer based on paramiko.
Credential priority: SSH Agent -> key file -> interactive getpass input.
Passwords and key contents must never appear in logs or exceptions.
"""

from __future__ import annotations

import getpass
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Empty
from typing import Optional

import paramiko

from src.config.settings import (
    SSH_DEFAULT_PORT,
    SSH_CONNECT_TIMEOUT,
    SSH_COMMAND_TIMEOUT,
    SSH_MAX_RETRIES,
    SSH_RETRY_DELAY,
    SSH_MAX_CONNECTIONS_PER_HOST,
    SSH_KEEPALIVE_INTERVAL,
    REDACTED_PLACEHOLDER,
)

logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    """SSH connection config"""
    host: str
    port: int = SSH_DEFAULT_PORT
    username: str = ""
    auth_method: str = "auto"  # auto | agent | key | password
    key_path: Optional[str] = None
    passphrase: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.username:
            self.username = os.getenv("USER", "root")

    def __repr__(self) -> str:
        """Ensure repr does not leak sensitive data"""
        return (
            f"SSHConfig(host={self.host!r}, port={self.port}, "
            f"username={self.username!r}, auth_method={self.auth_method!r}, "
            f"key_path={self.key_path!r}, passphrase={REDACTED_PLACEHOLDER!r})"
        )


class SSHConnectionError(Exception):
    """SSH connection error (no credentials exposed)"""

    def __init__(self, host: str, message: str) -> None:
        # Ensure no passwords in exception messages
        super().__init__(f"SSH connection failed [{host}]: {message}")
        self.host = host


class SSHConnectionManager:
    """
    SSH connection pool manager

    Features:
    - Per-host connection pool with connection reuse
    - Automatic retry mechanism
    - Command execution and SFTP file transfer
    - Secure credential handling
    """

    def __init__(self) -> None:
        # host -> Queue[paramiko.SSHClient]
        self._pools: dict[str, Queue[paramiko.SSHClient]] = defaultdict(
            lambda: Queue(maxsize=SSH_MAX_CONNECTIONS_PER_HOST)
        )
        self._configs: dict[str, SSHConfig] = {}
        self._lock = threading.Lock()
        logger.info("SSH connection manager initialized")

    def _create_client(self, config: SSHConfig) -> paramiko.SSHClient:
        """
        Create a new SSH connection

        Authentication priority:
        1. SSH Agent
        2. Key file (with optional passphrase)
        3. Interactive password input (getpass)
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": config.host,
            "port": config.port,
            "username": config.username,
            "timeout": SSH_CONNECT_TIMEOUT,
        }

        auth_method = config.auth_method

        if auth_method == "auto":
            # Try auth methods in order
            if self._try_agent_auth(client, connect_kwargs):
                return client
            if config.key_path and self._try_key_auth(client, connect_kwargs, config):
                return client
            if self._try_default_key_auth(client, connect_kwargs):
                return client
            # Fall back to password auth
            return self._password_auth(client, connect_kwargs, config)

        elif auth_method == "agent":
            if self._try_agent_auth(client, connect_kwargs):
                return client
            raise SSHConnectionError(config.host, "SSH Agent authentication failed")

        elif auth_method == "key":
            if config.key_path and self._try_key_auth(client, connect_kwargs, config):
                return client
            raise SSHConnectionError(config.host, "Key authentication failed, check key_path config")

        elif auth_method == "password":
            return self._password_auth(client, connect_kwargs, config)

        else:
            raise SSHConnectionError(config.host, f"Unsupported auth method: {auth_method}")

    @staticmethod
    def _try_agent_auth(
        client: paramiko.SSHClient, kwargs: dict
    ) -> bool:
        """Try SSH Agent authentication"""
        try:
            client.connect(**kwargs, allow_agent=True, look_for_keys=False)
            logger.debug("SSH Agent authentication succeeded: %s", kwargs["hostname"])
            return True
        except (paramiko.AuthenticationException, paramiko.SSHException):
            return False

    @staticmethod
    def _try_key_auth(
        client: paramiko.SSHClient,
        kwargs: dict,
        config: SSHConfig,
    ) -> bool:
        """Try key file authentication"""
        try:
            key_path = Path(config.key_path).expanduser()  # type: ignore[arg-type]
            if not key_path.exists():
                logger.debug("Key file not found: %s", key_path)
                return False

            client.connect(
                **kwargs,
                key_filename=str(key_path),
                passphrase=config.passphrase,
                allow_agent=False,
                look_for_keys=False,
            )
            logger.debug("Key authentication succeeded: %s", kwargs["hostname"])
            return True
        except (paramiko.AuthenticationException, paramiko.SSHException):
            return False

    @staticmethod
    def _try_default_key_auth(
        client: paramiko.SSHClient, kwargs: dict
    ) -> bool:
        """Try default key path authentication (~/.ssh/id_rsa etc.)"""
        try:
            client.connect(**kwargs, allow_agent=False, look_for_keys=True)
            logger.debug("Default key authentication succeeded: %s", kwargs["hostname"])
            return True
        except (paramiko.AuthenticationException, paramiko.SSHException):
            return False

    @staticmethod
    def _password_auth(
        client: paramiko.SSHClient,
        kwargs: dict,
        config: SSHConfig,
    ) -> paramiko.SSHClient:
        """
        Password authentication (interactive getpass only)

        Note: passwords never appear in logs or exceptions.
        """
        # Password obtained via getpass only, never from CLI args or env vars
        from src.utils.i18n import t
        password = getpass.getpass(
            prompt=t("ssh.password_prompt", user=config.username, host=config.host)
        )
        try:
            client.connect(
                **kwargs,
                password=password,
                allow_agent=False,
                look_for_keys=False,
            )
            logger.debug("Password authentication succeeded: %s (password securely handled)", kwargs["hostname"])
            return client
        except paramiko.AuthenticationException:
            raise SSHConnectionError(config.host, "Password authentication failed")
        finally:
            # Clear password variable ASAP
            del password

    def connect(self, config: SSHConfig) -> paramiko.SSHClient:
        """
        Get an SSH connection to the specified host

        Reuses from pool when available, creates new connection when empty. Supports auto-retry.
        """
        host_key = f"{config.host}:{config.port}"
        self._configs[host_key] = config

        # Try to get from pool
        pool = self._pools[host_key]
        try:
            client = pool.get_nowait()
            if client.get_transport() and client.get_transport().is_active():
                logger.debug("Reusing connection from pool: %s", host_key)
                return client
            # Connection stale, close and recreate
            client.close()
        except Empty:
            pass

        # Create new connection (with retry)
        last_error: Optional[Exception] = None
        for attempt in range(1, SSH_MAX_RETRIES + 1):
            try:
                client = self._create_client(config)
                transport = client.get_transport()
                if transport:
                    transport.set_keepalive(SSH_KEEPALIVE_INTERVAL)
                logger.info("SSH connection established: %s (attempt %d)", host_key, attempt)
                return client
            except SSHConnectionError:
                raise
            except Exception as e:
                last_error = e
                if attempt < SSH_MAX_RETRIES:
                    logger.warning(
                        "SSH connection failed [%s], retrying in %ds (%d/%d)",
                        host_key, SSH_RETRY_DELAY, attempt, SSH_MAX_RETRIES,
                    )
                    time.sleep(SSH_RETRY_DELAY)

        raise SSHConnectionError(
            config.host,
            f"Max retries exceeded ({SSH_MAX_RETRIES}), last error: {type(last_error).__name__}",
        )

    def release(self, config: SSHConfig, client: paramiko.SSHClient) -> None:
        """Return connection to pool"""
        host_key = f"{config.host}:{config.port}"
        pool = self._pools[host_key]

        if client.get_transport() and client.get_transport().is_active():
            try:
                pool.put_nowait(client)
                logger.debug("Connection returned to pool: %s", host_key)
            except Exception:
                # Pool full, close instead
                client.close()
        else:
            client.close()

    def execute_command(
        self,
        config: SSHConfig,
        command: str,
        timeout: int = SSH_COMMAND_TIMEOUT,
    ) -> tuple[int, str, str]:
        """
        Execute a command on a remote host

        Args:
            config: SSH config
            command: Command to execute
            timeout: Execution timeout in seconds

        Returns:
            (exit_code, stdout, stderr)
        """
        client = self.connect(config)
        try:
            logger.debug("Executing command [%s]: %s", config.host, command)

            _, stdout_ch, stderr_ch = client.exec_command(command, timeout=timeout)

            exit_code = stdout_ch.channel.recv_exit_status()
            stdout = stdout_ch.read().decode("utf-8", errors="replace")
            stderr = stderr_ch.read().decode("utf-8", errors="replace")

            logger.debug("Command completed [%s] exit_code=%d", config.host, exit_code)
            return exit_code, stdout, stderr

        except Exception as e:
            # Ensure no sensitive data in exception
            raise SSHConnectionError(
                config.host,
                f"Command execution failed: {type(e).__name__}",
            ) from None
        finally:
            self.release(config, client)

    def upload_file(
        self,
        config: SSHConfig,
        local_path: str | Path,
        remote_path: str,
    ) -> None:
        """Upload a file via SFTP"""
        client = self.connect(config)
        try:
            sftp = client.open_sftp()
            sftp.put(str(local_path), remote_path)
            sftp.close()
            logger.info("File uploaded: %s -> %s:%s", local_path, config.host, remote_path)
        except Exception as e:
            raise SSHConnectionError(
                config.host,
                f"File upload failed: {type(e).__name__}",
            ) from None
        finally:
            self.release(config, client)

    def download_file(
        self,
        config: SSHConfig,
        remote_path: str,
        local_path: str | Path,
    ) -> None:
        """Download a file via SFTP"""
        client = self.connect(config)
        try:
            sftp = client.open_sftp()
            sftp.get(remote_path, str(local_path))
            sftp.close()
            logger.info("File downloaded: %s:%s -> %s", config.host, remote_path, local_path)
        except Exception as e:
            raise SSHConnectionError(
                config.host,
                f"File download failed: {type(e).__name__}",
            ) from None
        finally:
            self.release(config, client)

    def close_all(self) -> None:
        """Close all connections and clear the pool"""
        with self._lock:
            for host_key, pool in self._pools.items():
                closed = 0
                while not pool.empty():
                    try:
                        client = pool.get_nowait()
                        client.close()
                        closed += 1
                    except Empty:
                        break
                if closed:
                    logger.info("Closed %d connections for %s", closed, host_key)
            self._pools.clear()
            self._configs.clear()
            logger.info("All SSH connections cleaned up")

    def __enter__(self) -> SSHConnectionManager:
        return self

    def __exit__(self, *args: object) -> None:
        self.close_all()
