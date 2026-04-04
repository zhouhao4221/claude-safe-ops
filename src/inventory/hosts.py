"""
Host inventory management

Loads host information from YAML config file, supports lookup by name, group, and tags.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.config.settings import HOSTS_CONFIG_PATH

logger = logging.getLogger(__name__)


@dataclass
class Host:
    """Host information"""
    hostname: str
    ip: str
    port: int = 22
    username: str = "root"
    group: str = "default"
    tags: list[str] = field(default_factory=list)
    auth_method: str = "auto"  # auto | agent | key | password
    key_path: Optional[str] = None
    description: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.hostname} ({self.ip})"


class HostInventory:
    """
    Host inventory

    Loads host list from YAML file, provides multi-dimensional query interface.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._hosts: dict[str, Host] = {}
        self._config_path = config_path or HOSTS_CONFIG_PATH

        if self._config_path.exists():
            self._load(self._config_path)

    def _load(self, path: Path) -> None:
        """Load host inventory from YAML file"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "hosts" not in data:
                logger.warning("Host config file is empty or malformed: %s", path)
                return

            for item in data["hosts"]:
                host = Host(
                    hostname=item["hostname"],
                    ip=item["ip"],
                    port=item.get("port", 22),
                    username=item.get("username", "root"),
                    group=item.get("group", "default"),
                    tags=item.get("tags", []),
                    auth_method=item.get("auth_method", "auto"),
                    key_path=item.get("key_path"),
                    description=item.get("description", ""),
                )
                self._hosts[host.hostname] = host

            logger.info("Loaded %d host configs: %s", len(self._hosts), path)

        except Exception:
            logger.exception("Failed to load host config: %s", path)

    def get_host(self, name: str) -> Optional[Host]:
        """Look up by hostname"""
        return self._hosts.get(name)

    def get_group(self, group_name: str) -> list[Host]:
        """Look up by group"""
        return [h for h in self._hosts.values() if h.group == group_name]

    def get_by_tag(self, tag: str) -> list[Host]:
        """Look up by tag"""
        return [h for h in self._hosts.values() if tag in h.tags]

    def list_all(self) -> list[Host]:
        """List all hosts"""
        return list(self._hosts.values())

    def groups(self) -> list[str]:
        """List all group names"""
        return sorted(set(h.group for h in self._hosts.values()))

    def tags(self) -> list[str]:
        """List all tags"""
        all_tags: set[str] = set()
        for h in self._hosts.values():
            all_tags.update(h.tags)
        return sorted(all_tags)

    def add_host(self, host: Host) -> None:
        """Dynamically add a host"""
        self._hosts[host.hostname] = host

    def remove_host(self, name: str) -> bool:
        """Remove a host"""
        if name in self._hosts:
            del self._hosts[name]
            return True
        return False

    def __len__(self) -> int:
        return len(self._hosts)

    def __contains__(self, name: str) -> bool:
        return name in self._hosts
