"""Host metadata cache.

Persists a per-host fingerprint (OS, hardware, key software) under
``~/.claude-safe-ops/cache/hosts/<host>.json`` so that subsequent connects can
show machine context instantly without re-running probe commands.

Two independent TTLs are tracked:
  * ``fingerprint`` — hardware / OS info (rarely changes, 24h default)
  * ``software``    — installed software inventory (12h default)

The caller (usually ``HostSession``) decides when to call ``get_or_fetch``;
failures to collect are logged but never raise, so a broken probe can never
block a connection.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.config.settings import (
    HOST_CACHE_TTL_SECONDS,
    SOFTWARE_CACHE_TTL_SECONDS,
    USER_HOST_CACHE_DIR,
)

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_lock = threading.Lock()


def _safe_filename(host: str) -> str:
    """Normalize a host identifier into a filesystem-safe filename stem."""
    cleaned = _SAFE_NAME_RE.sub("_", host.strip())
    return cleaned or "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _age_seconds(iso_ts: Optional[str]) -> float:
    if not iso_ts:
        return float("inf")
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return float("inf")
    return (datetime.now(dt.tzinfo or timezone.utc) - dt).total_seconds()


@dataclass
class HostMetadata:
    """In-memory view of a cached host record."""

    host: str
    data: Dict[str, Any]

    @property
    def fingerprint(self) -> Dict[str, Any]:
        return self.data.get("fingerprint") or {}

    @property
    def software(self) -> Dict[str, Any]:
        return self.data.get("software") or {}

    def summary_line(self) -> str:
        """One-line human summary used when a connection is established."""
        fp = self.fingerprint
        os_name = fp.get("os") or fp.get("os_id") or "unknown OS"
        kernel = fp.get("kernel", "")
        cpu = fp.get("cpu") or {}
        mem = fp.get("memory_total", "")
        sw = ", ".join(sorted(self.software.keys())[:6]) or "-"
        return (
            f"{os_name} | kernel {kernel} | "
            f"{cpu.get('cores', '?')} cores {cpu.get('model', '').strip()} | "
            f"mem {mem} | sw: {sw}"
        )


class HostMetadataCache:
    """File-backed cache of host fingerprints.

    Not a singleton — instances are cheap. A module-level lock serializes
    writes so that concurrent ``HostSession`` instances can't corrupt files.
    """

    def __init__(self, cache_dir: Path = USER_HOST_CACHE_DIR) -> None:
        self._dir = Path(cache_dir)

    # ------------------------------------------------------------------ load/save

    def _path(self, host: str) -> Path:
        return self._dir / f"{_safe_filename(host)}.json"

    def load(self, host: str) -> Optional[HostMetadata]:
        path = self._path(host)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read host cache %s: %s", path, e)
            return None
        return HostMetadata(host=host, data=data)

    def save(self, host: str, data: Dict[str, Any]) -> None:
        path = self._path(host)
        with _lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                os.replace(tmp, path)
            except OSError as e:
                logger.warning("Failed to write host cache %s: %s", path, e)

    # ------------------------------------------------------------------ staleness

    def is_fingerprint_stale(self, meta: Optional[HostMetadata], ttl: int = HOST_CACHE_TTL_SECONDS) -> bool:
        if meta is None or not meta.fingerprint:
            return True
        return _age_seconds(meta.data.get("fingerprint_collected_at")) > ttl

    def is_software_stale(self, meta: Optional[HostMetadata], ttl: int = SOFTWARE_CACHE_TTL_SECONDS) -> bool:
        if meta is None or not meta.software:
            return True
        return _age_seconds(meta.data.get("software_collected_at")) > ttl

    # ------------------------------------------------------------------ main API

    def get_or_fetch(
        self,
        session: "HostSession",  # noqa: F821  (forward ref)
        *,
        force: bool = False,
        software: bool = True,
    ) -> HostMetadata:
        """Return cached metadata for ``session.host``, collecting what's stale.

        Never raises — on collection failure the previous cached value (or an
        empty record) is kept and returned.
        """
        host = session.host
        meta = self.load(host)
        data: Dict[str, Any] = meta.data if meta else {"host": host}

        need_fp = force or self.is_fingerprint_stale(meta)
        need_sw = software and (force or self.is_software_stale(meta))

        if not (need_fp or need_sw):
            return meta  # type: ignore[return-value]

        # Lazy import to avoid a circular dependency (modules.system imports executor)
        from src.modules.system.ops import SystemOps

        ops = SystemOps(session)

        if need_fp:
            try:
                data["fingerprint"] = ops.collect_fingerprint()
                data["fingerprint_collected_at"] = _now_iso()
            except Exception as e:  # noqa: BLE001
                logger.warning("collect_fingerprint failed for %s: %s", host, e)

        if need_sw:
            try:
                data["software"] = ops.collect_software()
                data["software_collected_at"] = _now_iso()
            except Exception as e:  # noqa: BLE001
                logger.warning("collect_software failed for %s: %s", host, e)

        data["host"] = host
        self.save(host, data)
        return HostMetadata(host=host, data=data)
