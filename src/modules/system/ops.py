"""System operations module providing system info queries, service management, user management, and more."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.config.settings import (
    DEFAULT_SOFTWARE_PROBES_PATH,
    SOFTWARE_PROBES_CONFIG_PATH,
)
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

    # ------------------------------------------------------------------
    # Host fingerprint (for metadata cache)
    # ------------------------------------------------------------------

    def collect_fingerprint(self) -> Dict[str, Any]:
        """Collect a compact hardware / OS fingerprint (all LOW-risk read-only commands).

        Returns a dict suitable for JSON serialization. Missing fields degrade to
        empty strings / lists rather than raising, so that partial data from a
        minimal / non-Linux host is still cached.
        """
        script = (
            "echo '<<<uname>>>'; uname -a 2>/dev/null; "
            "echo '<<<os_release>>>'; cat /etc/os-release 2>/dev/null; "
            "echo '<<<hostname>>>'; hostname 2>/dev/null; "
            "echo '<<<ips>>>'; (hostname -I 2>/dev/null || ip -4 -o addr show 2>/dev/null | awk '{print $4}'); "
            "echo '<<<cpu_model>>>'; grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2-; "
            "echo '<<<cpu_cores>>>'; (nproc 2>/dev/null || grep -c '^processor' /proc/cpuinfo 2>/dev/null); "
            "echo '<<<mem_total>>>'; free -h 2>/dev/null | awk '/^Mem:/ {print $2}'; "
            "echo '<<<disks>>>'; df -hT -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2; "
            "echo '<<<uptime>>>'; uptime -p 2>/dev/null || uptime 2>/dev/null; "
            "echo '<<<running_services>>>'; systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1}' | head -40; "
            "echo '<<<end>>>'"
        )
        result = self._exec.execute(script)
        sections = _split_sections(result.stdout)

        uname_line = (sections.get("uname") or "").strip()
        uname_parts = uname_line.split()
        kernel = uname_parts[2] if len(uname_parts) >= 3 else ""
        arch = uname_parts[-2] if len(uname_parts) >= 2 else ""

        os_release = _parse_kv(sections.get("os_release", ""))
        os_pretty = os_release.get("PRETTY_NAME") or os_release.get("NAME") or ""

        ips_raw = (sections.get("ips") or "").split()
        ips = [ip.split("/")[0] for ip in ips_raw if ip]

        try:
            cpu_cores = int((sections.get("cpu_cores") or "0").strip() or 0)
        except ValueError:
            cpu_cores = 0

        disks: List[Dict[str, str]] = []
        for line in (sections.get("disks") or "").splitlines():
            cols = line.split()
            if len(cols) >= 7:
                disks.append({
                    "device": cols[0],
                    "fstype": cols[1],
                    "size": cols[2],
                    "used": cols[3],
                    "avail": cols[4],
                    "use_pct": cols[5],
                    "mount": cols[6],
                })

        services = [s for s in (sections.get("running_services") or "").split() if s.endswith(".service")]

        return {
            "os": os_pretty,
            "os_id": os_release.get("ID", ""),
            "os_version": os_release.get("VERSION_ID", ""),
            "kernel": kernel,
            "arch": arch,
            "hostname_remote": (sections.get("hostname") or "").strip(),
            "ips": ips,
            "cpu": {
                "model": (sections.get("cpu_model") or "").strip(),
                "cores": cpu_cores,
            },
            "memory_total": (sections.get("mem_total") or "").strip(),
            "disks": disks,
            "uptime": (sections.get("uptime") or "").strip(),
            "running_services": services,
        }

    def collect_software(self, probes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
        """Probe the remote host for commonly used software and return a mapping
        ``{name: {version, bin, config, conf_dir, data_dir, log_dir, service, status}}``.

        Only the entries whose ``detect`` command exits 0 are included. Each probe
        is an independent LOW-risk shell command; failures are swallowed so that
        one broken probe does not drop the whole result.
        """
        if probes is None:
            probes = _load_software_probes()

        # Build one big shell script that runs all probes with clear markers.
        # Using ``|| true`` so every section always terminates normally.
        lines: List[str] = []
        for probe in probes:
            name = probe.get("name", "").strip()
            if not name:
                continue
            detect = probe.get("detect", "false")
            marker = f"<<<SW:{name}>>>"
            lines.append(f"echo '{marker}'")
            lines.append(f"if {detect} >/dev/null 2>&1; then")
            lines.append("  echo 'INSTALLED=1'")
            if probe.get("bin"):
                lines.append(f"  echo \"BIN=$({probe['bin']} 2>/dev/null | head -1)\"")
            if probe.get("version"):
                lines.append(f"  echo \"VERSION=$({probe['version']} 2>/dev/null | head -2 | tr '\\n' ' ')\"")
            for cfg in probe.get("config", []) or []:
                lines.append(f"  [ -e {shlex.quote(cfg)} ] && echo 'CONFIG={cfg}'")
            for cdir in probe.get("conf_dir", []) or []:
                lines.append(f"  [ -d {shlex.quote(cdir)} ] && echo 'CONF_DIR={cdir}'")
            for ddir in probe.get("data_dir", []) or []:
                lines.append(f"  [ -d {shlex.quote(ddir)} ] && echo 'DATA_DIR={ddir}'")
            for ldir in probe.get("log_dir", []) or []:
                lines.append(f"  [ -e {shlex.quote(ldir)} ] && echo 'LOG_DIR={ldir}'")
            if probe.get("service"):
                svc = probe["service"]
                lines.append(
                    f"  echo \"SERVICE={svc}\"; "
                    f"echo \"STATUS=$(systemctl is-active {svc} 2>/dev/null || echo unknown)\""
                )
            lines.append("else echo 'INSTALLED=0'; fi")
        lines.append("echo '<<<SW:end>>>'")
        script = " ; ".join(lines)

        result = self._exec.execute(script)
        return _parse_software_output(result.stdout)


# ------------------------------------------------------------------
# Helpers (module-level, tested via collect_* methods)
# ------------------------------------------------------------------

_SECTION_RE = re.compile(r"^<<<([a-zA-Z_]+)>>>\s*$", re.MULTILINE)


def _split_sections(text: str) -> Dict[str, str]:
    """Split stdout produced by collect_fingerprint into {section: body}."""
    if not text:
        return {}
    out: Dict[str, str] = {}
    parts = _SECTION_RE.split(text)
    # parts = ['', name1, body1, name2, body2, ...]
    it = iter(parts[1:])
    for name, body in zip(it, it):
        if name == "end":
            break
        out[name] = body.strip("\n")
    return out


def _parse_kv(text: str) -> Dict[str, str]:
    """Parse KEY="value" lines (os-release style)."""
    result: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _parse_software_output(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse the marker-delimited output of collect_software."""
    result: Dict[str, Dict[str, Any]] = {}
    if not text:
        return result
    current: Optional[str] = None
    entry: Dict[str, Any] = {}
    installed = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("<<<SW:") and line.endswith(">>>"):
            if current and installed:
                result[current] = entry
            name = line[6:-3]
            if name == "end":
                current = None
                break
            current = name
            entry = {}
            installed = False
            continue
        if current is None:
            continue
        if line == "INSTALLED=1":
            installed = True
        elif line == "INSTALLED=0":
            installed = False
        elif "=" in line:
            k, _, v = line.partition("=")
            key = k.strip().lower()
            val = v.strip()
            if key in ("config", "conf_dir", "data_dir", "log_dir"):
                entry.setdefault(key, []).append(val)
            else:
                entry[key] = val
    if current and installed:
        result[current] = entry
    return result


def _load_software_probes() -> List[Dict[str, Any]]:
    """Load software probes list. User override fully replaces the built-in list."""
    for path in (SOFTWARE_PROBES_CONFIG_PATH, DEFAULT_SOFTWARE_PROBES_PATH):
        if Path(path).exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                probes = data.get("probes") or []
                if isinstance(probes, list):
                    return probes
            except Exception:
                continue
    return []
