"""
Playbook Manager

Responsible for loading, saving, deleting, and template rendering of playbooks.
Playbook sources: built-in (src/config/playbooks/) and user-defined (~/.claude-safe-ops/playbooks/).
When names conflict, user playbooks override built-in ones.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.config.settings import DEFAULT_PLAYBOOK_DIR, USER_PLAYBOOK_DIR

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class PlaybookStep:
    """A single playbook step"""
    name: str
    command: str        # May contain {{var}} template variables
    on_fail: str = "stop"  # "stop" | "continue"


@dataclass
class Playbook:
    """Playbook data structure"""
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    vars: dict[str, str] = field(default_factory=dict)
    steps: list[PlaybookStep] = field(default_factory=list)
    notes: str = ""
    source: str = "user"    # "builtin" | "user"
    path: Path = field(default_factory=lambda: Path())


class PlaybookManager:
    """
    Playbook Manager

    Loads and merges built-in and user playbooks, provides CRUD and template rendering.
    """

    def __init__(
        self,
        builtin_dir: Path = DEFAULT_PLAYBOOK_DIR,
        user_dir: Path = USER_PLAYBOOK_DIR,
    ) -> None:
        self._builtin_dir = builtin_dir
        self._user_dir = user_dir

    def list_all(self, tag: Optional[str] = None) -> list[Playbook]:
        """
        List all playbooks; user playbooks override built-in ones with the same name.

        Args:
            tag: Optional tag filter
        """
        playbooks: dict[str, Playbook] = {}

        # Load built-in first
        for pb in self._load_dir(self._builtin_dir, source="builtin"):
            playbooks[pb.name] = pb

        # Then load user (same name overrides)
        for pb in self._load_dir(self._user_dir, source="user"):
            playbooks[pb.name] = pb

        result = sorted(playbooks.values(), key=lambda p: p.name)

        if tag:
            result = [p for p in result if tag in p.tags]

        return result

    def get(self, name: str) -> Optional[Playbook]:
        """Get a playbook by name (user takes priority)"""
        # Check user directory first
        user_path = self._user_dir / f"{name}.yaml"
        if user_path.exists():
            return self._load_file(user_path, source="user")

        # Then check built-in directory
        builtin_path = self._builtin_dir / f"{name}.yaml"
        if builtin_path.exists():
            return self._load_file(builtin_path, source="builtin")

        return None

    def save(self, playbook: Playbook) -> Path:
        """Save a playbook to the user directory"""
        self._user_dir.mkdir(parents=True, exist_ok=True)
        path = self._user_dir / f"{playbook.name}.yaml"

        data = {
            "name": playbook.name,
            "description": playbook.description,
            "tags": playbook.tags,
        }
        if playbook.vars:
            data["vars"] = playbook.vars
        data["steps"] = []
        for step in playbook.steps:
            step_data: dict = {"name": step.name, "command": step.command}
            if step.on_fail != "stop":
                step_data["on_fail"] = step.on_fail
            data["steps"].append(step_data)
        if playbook.notes:
            data["notes"] = playbook.notes

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info("Playbook saved: %s", path)
        return path

    def delete(self, name: str) -> bool:
        """Delete a user playbook (built-in playbooks cannot be deleted)"""
        path = self._user_dir / f"{name}.yaml"
        if path.exists():
            path.unlink()
            logger.info("Playbook deleted: %s", path)
            return True
        return False

    @staticmethod
    def render_command(command: str, variables: dict[str, str]) -> str:
        """Replace {{var}} placeholders in a command with actual values"""
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in variables:
                return variables[var_name]
            return match.group(0)  # Keep undefined variables as-is

        return _VAR_PATTERN.sub(replacer, command)

    @staticmethod
    def extract_vars(playbook: Playbook) -> set[str]:
        """Extract all variable names used in a playbook"""
        var_names: set[str] = set()
        for step in playbook.steps:
            var_names.update(_VAR_PATTERN.findall(step.command))
        return var_names

    # -- Internal methods ─────────────────────────────────────────

    def _load_dir(self, directory: Path, source: str) -> list[Playbook]:
        """Load all .yaml playbooks from a directory"""
        if not directory.exists():
            return []

        playbooks: list[Playbook] = []
        for path in sorted(directory.glob("*.yaml")):
            pb = self._load_file(path, source)
            if pb:
                playbooks.append(pb)
        return playbooks

    @staticmethod
    def _load_file(path: Path, source: str) -> Optional[Playbook]:
        """Load a playbook from a single YAML file"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "name" not in data or "steps" not in data:
                logger.warning("Invalid playbook format, skipping: %s", path)
                return None

            steps = []
            for s in data["steps"]:
                steps.append(PlaybookStep(
                    name=s["name"],
                    command=s["command"],
                    on_fail=s.get("on_fail", "stop"),
                ))

            return Playbook(
                name=data["name"],
                description=data.get("description", ""),
                tags=data.get("tags", []),
                vars=data.get("vars", {}),
                steps=steps,
                notes=data.get("notes", ""),
                source=source,
                path=path,
            )

        except Exception:
            logger.exception("Failed to load playbook: %s", path)
            return None
