"""Disk operations module providing disk usage, inode, block device, LVM, and I/O statistics functions."""

from __future__ import annotations

from src.executor import HostSession, CommandResult


class DiskOps:
    """Disk operations collection covering space usage, device info, health checks, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize disk operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Disk Usage
    # ------------------------------------------------------------------

    def get_disk_usage(self) -> CommandResult:
        """Get disk usage for each mount point in human-readable format."""
        return self._exec.execute("df -h")

    def get_inode_usage(self) -> CommandResult:
        """Get inode usage for each mount point."""
        return self._exec.execute("df -i")

    # ------------------------------------------------------------------
    # Block Devices and Mounts
    # ------------------------------------------------------------------

    def get_block_devices(self) -> CommandResult:
        """List all block devices with their mount points, sizes, types, etc."""
        return self._exec.execute("lsblk")

    def get_mount_info(self) -> CommandResult:
        """Get current mount information (formatted output)."""
        return self._exec.execute("mount | column -t")

    # ------------------------------------------------------------------
    # Directory and File Analysis
    # ------------------------------------------------------------------

    def get_large_files(self, path: str = "/", top_n: int = 20) -> CommandResult:
        """Find the largest files/directories under the specified path.

        Args:
            path: Directory path to scan, defaults to root.
            top_n: Return the top N largest items, default 20.
        """
        cmd = f"du -ah {path} 2>/dev/null | sort -rh | head -n {top_n}"
        return self._exec.execute(cmd, timeout=120)

    def get_dir_size(self, path: str) -> CommandResult:
        """Get the total size of a specified directory.

        Args:
            path: Directory path.
        """
        return self._exec.execute(f"du -sh {path} 2>/dev/null")

    # ------------------------------------------------------------------
    # Health Checks
    # ------------------------------------------------------------------

    def check_disk_health(self) -> CommandResult:
        """Check disk SMART health status (requires smartctl tool and root privileges)."""
        cmd = (
            "if command -v smartctl &>/dev/null; then "
            "  for dev in $(lsblk -dnp -o NAME); do "
            "    echo \"=== $dev ===\"; "
            "    smartctl -H $dev 2>/dev/null || echo 'cannot read SMART for this device'; "
            "  done; "
            "else "
            "  echo 'smartctl not installed (smartmontools)'; "
            "fi"
        )
        return self._exec.execute(cmd, timeout=60)

    # ------------------------------------------------------------------
    # LVM
    # ------------------------------------------------------------------

    def get_lvm_info(self) -> CommandResult:
        """Get LVM physical volume, volume group, and logical volume information."""
        cmd = (
            "echo '=== Physical Volumes ===' && pvs 2>/dev/null || echo 'pvs not available' && "
            "echo '=== Volume Groups ===' && vgs 2>/dev/null || echo 'vgs not available' && "
            "echo '=== Logical Volumes ===' && lvs 2>/dev/null || echo 'lvs not available'"
        )
        return self._exec.execute(cmd)

    # ------------------------------------------------------------------
    # I/O Statistics
    # ------------------------------------------------------------------

    def get_io_stats(self) -> CommandResult:
        """Get disk I/O statistics (requires iostat tool)."""
        cmd = (
            "if command -v iostat &>/dev/null; then "
            "  iostat -x 1 3; "
            "else "
            "  echo 'iostat not installed (sysstat package)'; "
            "  echo '=== /proc/diskstats ===' && cat /proc/diskstats; "
            "fi"
        )
        return self._exec.execute(cmd, timeout=30)
