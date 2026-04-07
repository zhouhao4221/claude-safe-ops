#!/usr/bin/env bash
# host-info.sh — show / refresh cached host metadata for Claude Code mode.
#
# Usage:
#   scripts/host-info.sh <ssh-alias>            # print cache, refresh if stale/missing
#   scripts/host-info.sh <ssh-alias> --force    # always re-collect
#   scripts/host-info.sh <ssh-alias> --software # refresh only software section
#
# The script is a thin wrapper around the Python cache module so that both
# the Python CLI and Claude Code mode share the same storage at
# ~/.claude-safe-ops/cache/hosts/<alias>.json

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <ssh-alias> [--force] [--software]" >&2
    exit 2
fi

HOST="$1"; shift || true
FORCE=0
SOFTWARE_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --force)    FORCE=1 ;;
        --software) SOFTWARE_ONLY=1 ;;
        *) echo "Unknown flag: $arg" >&2; exit 2 ;;
    esac
done

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CACHE_DIR="$HOME/.claude-safe-ops/cache/hosts"
CACHE_FILE="$CACHE_DIR/${HOST//\//_}.json"

mkdir -p "$CACHE_DIR"

# If a valid cache exists and no refresh is requested, just print it.
if [[ $FORCE -eq 0 && $SOFTWARE_ONLY -eq 0 && -s "$CACHE_FILE" ]]; then
    # Check staleness via python (TTL from settings.py)
    if python3 -c "
import json, sys, datetime
from src.config.settings import HOST_CACHE_TTL_SECONDS
data = json.load(open('$CACHE_FILE'))
ts = data.get('fingerprint_collected_at')
if not ts:
    sys.exit(1)
age = (datetime.datetime.now(datetime.datetime.fromisoformat(ts).tzinfo) - datetime.datetime.fromisoformat(ts)).total_seconds()
sys.exit(0 if age <= HOST_CACHE_TTL_SECONDS else 1)
" 2>/dev/null; then
        cat "$CACHE_FILE"
        exit 0
    fi
fi

# Refresh: run probes over ssh and rebuild the JSON.
# We execute a single remote script whose output is parsed by a short python helper.
REMOTE_SCRIPT='
echo "<<<uname>>>"; uname -a 2>/dev/null
echo "<<<os_release>>>"; cat /etc/os-release 2>/dev/null
echo "<<<hostname>>>"; hostname 2>/dev/null
echo "<<<ips>>>"; hostname -I 2>/dev/null || ip -4 -o addr show 2>/dev/null | awk "{print \$4}"
echo "<<<cpu_model>>>"; grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2-
echo "<<<cpu_cores>>>"; nproc 2>/dev/null || grep -c "^processor" /proc/cpuinfo 2>/dev/null
echo "<<<mem_total>>>"; free -h 2>/dev/null | awk "/^Mem:/ {print \$2}"
echo "<<<disks>>>"; df -hT -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2
echo "<<<uptime>>>"; uptime -p 2>/dev/null || uptime 2>/dev/null
echo "<<<end>>>"
'

REMOTE_OUT=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" "$REMOTE_SCRIPT" 2>/dev/null || true)
if [[ -z "$REMOTE_OUT" ]]; then
    echo "Failed to reach '$HOST' via ssh." >&2
    [[ -s "$CACHE_FILE" ]] && { cat "$CACHE_FILE"; exit 0; }
    exit 1
fi

cd "$PROJECT_DIR"
REMOTE_OUT="$REMOTE_OUT" HOST="$HOST" CACHE_FILE="$CACHE_FILE" python3 <<'PY'
import json, os, re, datetime, pathlib
text = os.environ["REMOTE_OUT"]
host = os.environ["HOST"]
cache_file = pathlib.Path(os.environ["CACHE_FILE"])

parts = re.split(r"^<<<([a-zA-Z_]+)>>>\s*$", text, flags=re.M)
sections = {}
it = iter(parts[1:])
for name, body in zip(it, it):
    if name == "end":
        break
    sections[name] = body.strip("\n")

def kv(t):
    d = {}
    for line in t.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d

osr = kv(sections.get("os_release", ""))
uname_parts = (sections.get("uname") or "").split()
kernel = uname_parts[2] if len(uname_parts) >= 3 else ""
arch = uname_parts[-2] if len(uname_parts) >= 2 else ""
ips = [ip.split("/")[0] for ip in (sections.get("ips") or "").split() if ip]

disks = []
for line in (sections.get("disks") or "").splitlines():
    cols = line.split()
    if len(cols) >= 7:
        disks.append({"device": cols[0], "fstype": cols[1], "size": cols[2],
                      "used": cols[3], "avail": cols[4], "use_pct": cols[5], "mount": cols[6]})

try:
    cores = int((sections.get("cpu_cores") or "0").strip() or 0)
except ValueError:
    cores = 0

existing = {}
if cache_file.exists():
    try:
        existing = json.loads(cache_file.read_text())
    except Exception:
        existing = {}

existing["host"] = host
existing["fingerprint"] = {
    "os": osr.get("PRETTY_NAME") or osr.get("NAME") or "",
    "os_id": osr.get("ID", ""),
    "os_version": osr.get("VERSION_ID", ""),
    "kernel": kernel,
    "arch": arch,
    "hostname_remote": (sections.get("hostname") or "").strip(),
    "ips": ips,
    "cpu": {"model": (sections.get("cpu_model") or "").strip(), "cores": cores},
    "memory_total": (sections.get("mem_total") or "").strip(),
    "disks": disks,
    "uptime": (sections.get("uptime") or "").strip(),
}
existing["fingerprint_collected_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

cache_file.parent.mkdir(parents=True, exist_ok=True)
tmp = cache_file.with_suffix(".json.tmp")
tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
tmp.replace(cache_file)
print(json.dumps(existing, ensure_ascii=False, indent=2))
PY
