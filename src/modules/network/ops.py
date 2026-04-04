"""Network operations module providing network interface, routing, connectivity testing, port and firewall query functions."""

from __future__ import annotations

from src.executor import HostSession, CommandResult


class NetworkOps:
    """Network operations collection covering interface queries, routing, connectivity tests, port checks, and other routine tasks."""

    def __init__(self, session: HostSession) -> None:
        """Initialize network operations.

        Args:
            session: Host session instance.
        """
        self._exec = session

    # ------------------------------------------------------------------
    # Network Interfaces and Routing
    # ------------------------------------------------------------------

    def get_interfaces(self) -> CommandResult:
        """Get address information for all network interfaces."""
        return self._exec.execute("ip addr show")

    def get_routing_table(self) -> CommandResult:
        """Get the system routing table."""
        return self._exec.execute("ip route show")

    def get_dns_config(self) -> CommandResult:
        """Get DNS resolver configuration."""
        return self._exec.execute("cat /etc/resolv.conf")

    # ------------------------------------------------------------------
    # Connectivity Testing
    # ------------------------------------------------------------------

    def check_connectivity(self, target: str) -> CommandResult:
        """Check connectivity to a target host via ping (sends 4 packets).

        Args:
            target: Target hostname or IP address.
        """
        return self._exec.execute(f"ping -c 4 {target}", timeout=30)

    def traceroute(self, target: str) -> CommandResult:
        """Perform a traceroute to the target host.

        Args:
            target: Target hostname or IP address.
        """
        return self._exec.execute(
            f"traceroute {target} 2>/dev/null || tracepath {target} 2>/dev/null",
            timeout=60,
        )

    # ------------------------------------------------------------------
    # Ports and Connections
    # ------------------------------------------------------------------

    def get_listening_ports(self) -> CommandResult:
        """Get all TCP listening ports and associated processes."""
        return self._exec.execute("ss -tlnp")

    def get_connections(self) -> CommandResult:
        """Get all current TCP connections and associated processes."""
        return self._exec.execute("ss -tnp")

    def check_port(self, host: str, port: int) -> CommandResult:
        """Check whether a specific port on a host is reachable.

        Args:
            host: Target hostname or IP.
            port: Target port number.
        """
        cmd = (
            f"nc -zv -w 3 {host} {port} 2>&1 || "
            f"(echo | timeout 3 bash -c 'cat < /dev/tcp/{host}/{port}' && "
            f"echo 'port {port} is open' || echo 'port {port} is closed') 2>&1"
        )
        return self._exec.execute(cmd, timeout=15)

    # ------------------------------------------------------------------
    # Firewall and Traffic
    # ------------------------------------------------------------------

    def get_firewall_rules(self) -> CommandResult:
        """Get iptables firewall rules (requires root privileges)."""
        return self._exec.execute(
            "iptables -L -n -v 2>/dev/null || echo 'iptables not available or no permission'"
        )

    def get_bandwidth(self) -> CommandResult:
        """Get traffic statistics for each network interface (parsed from /proc/net/dev)."""
        cmd = (
            "echo '=== /proc/net/dev ===' && cat /proc/net/dev && "
            "echo '=== Formatted ===' && "
            "awk 'NR>2{gsub(/:/, \" \"); "
            "printf \"%-12s RX=%-15s TX=%-15s\\n\", $1, $2, $10}' /proc/net/dev"
        )
        return self._exec.execute(cmd)
