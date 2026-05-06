"""Network device discovery - scans IP ranges for responsive devices via SNMP, ping, or TCP ports."""

import asyncio
import platform
import socket
from typing import Any, Optional

from .spike_snmp import get_sys_descr

# Common ports to scan for non-SNMP discovery
COMMON_PORTS = [22, 80, 443, 445, 3389, 8291, 8728, 8080, 53, 21, 23, 161, 162]

# Port-to-service mapping for human-readable descriptions
PORT_SERVICES = {
    22: "SSH",
    80: "HTTP",
    443: "HTTPS",
    445: "SMB",
    3389: "RDP",
    8291: "WinBox",
    8728: "RouterOS API",
    8080: "HTTP-Alt",
    53: "DNS",
    21: "FTP",
    23: "Telnet",
    161: "SNMP",
    162: "SNMP-Trap",
}


async def discover_devices(
    network_range: str,
    community: str = "public",
    timeout: float = 1.0,
    max_concurrent: int = 50,
    method: str = "all",
) -> list[dict[str, Any]]:
    """
    Discover responsive devices in a network range.

    Args:
        network_range: CIDR notation (e.g., "192.168.1.0/24") or IP range
        community: SNMP community string (used when method includes snmp)
        timeout: Timeout per host in seconds
        max_concurrent: Maximum concurrent probes
        method: Discovery method - "snmp", "ping", "port", or "all"

    Returns:
        List of discovered devices with ip_address, sys_descr, discovery_method, open_ports
    """
    import ipaddress

    # Parse network range
    try:
        network = ipaddress.ip_network(network_range, strict=False)
    except ValueError:
        return await _discover_range(network_range, community, timeout, max_concurrent, method)

    hosts = [str(host) for host in network.hosts()]
    return await _scan_hosts(hosts, community, timeout, max_concurrent, method)


async def _discover_range(
    range_str: str,
    community: str,
    timeout: float,
    max_concurrent: int,
    method: str,
) -> list[dict[str, Any]]:
    """Discover devices in a simple IP range like 192.168.1.1-100."""
    parts = range_str.split("-")
    if len(parts) != 2:
        return []

    base_parts = parts[0].rsplit(".", 1)
    if len(base_parts) != 2:
        return []

    base_prefix = base_parts[0]
    start = int(base_parts[1])
    end = int(parts[1])

    hosts = [f"{base_prefix}.{i}" for i in range(start, end + 1)]
    return await _scan_hosts(hosts, community, timeout, max_concurrent, method)


async def _scan_hosts(
    hosts: list[str],
    community: str,
    timeout: float,
    max_concurrent: int,
    method: str,
) -> list[dict[str, Any]]:
    """Scan a list of hosts using the specified discovery method."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def scan_host(host: str) -> Optional[dict[str, Any]]:
        async with semaphore:
            device = await _probe_host(host, community, timeout, method)
            if device:
                results.append(device)
            return device

    await asyncio.gather(
        *[scan_host(host) for host in hosts],
        return_exceptions=True
    )

    return results


async def _probe_host(
    host: str, community: str, timeout: float, method: str
) -> Optional[dict[str, Any]]:
    """Probe a single host using the requested discovery method(s)."""
    snmp_result = None
    ping_alive = False
    open_ports: list[int] = []

    # SNMP discovery
    if method in ("snmp", "all"):
        snmp_result = await _probe_snmp(host, community, timeout)
        if snmp_result:
            snmp_result["discovery_method"] = "snmp"
            return snmp_result

    # ICMP ping discovery
    if method in ("ping", "all"):
        ping_alive = await _probe_ping(host, timeout)

    # TCP port scan discovery
    if method in ("port", "all"):
        open_ports = await _probe_ports(host, timeout)

    # If ping or ports found something, create a non-SNMP device record
    if ping_alive or open_ports:
        parts = []
        if ping_alive:
            parts.append("Host alive (ICMP ping)")
        if open_ports:
            services = ", ".join(
                f"{p} ({PORT_SERVICES.get(p, 'unknown')})" for p in open_ports[:6]
            )
            parts.append(f"Open ports: {services}")
            if len(open_ports) > 6:
                parts.append(f"...and {len(open_ports) - 6} more")

        return {
            "ip_address": host,
            "sys_descr": "; ".join(parts),
            "community": community,
            "discovery_method": "ping" if ping_alive and not open_ports else "port",
            "open_ports": open_ports,
            "status": "discovered",
        }

    return None


async def _probe_snmp(
    host: str, community: str, timeout: float
) -> Optional[dict[str, Any]]:
    """Probe a single host via SNMP."""
    # Quick TCP check on port 161 before attempting SNMP
    port_open = await _check_port(host, 161, timeout)
    if not port_open:
        return None

    loop = asyncio.get_event_loop()
    try:
        sys_descr = await asyncio.wait_for(
            loop.run_in_executor(None, get_sys_descr, host, community),
            timeout=timeout * 2,
        )
        if sys_descr:
            return {
                "ip_address": host,
                "sys_descr": sys_descr,
                "community": community,
                "discovery_method": "snmp",
                "open_ports": [161],
                "status": "discovered",
            }
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass

    return None


async def _probe_ping(host: str, timeout: float) -> bool:
    """Check if a host responds to ICMP ping."""
    system = platform.system().lower()
    if system == "windows":
        ping_cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    else:
        ping_cmd = ["ping", "-c", "1", "-W", str(int(timeout)), host]

    try:
        process = await asyncio.create_subprocess_exec(
            *ping_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout + 3,
        )
        return process.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return False


async def _probe_ports(host: str, timeout: float) -> list[int]:
    """Scan common TCP ports and return a list of open ports."""
    semaphore = asyncio.Semaphore(10)  # Limit concurrent port scans per host
    open_ports: list[int] = []

    async def check_port(port: int) -> None:
        async with semaphore:
            if await _check_port(host, port, timeout):
                open_ports.append(port)

    await asyncio.gather(
        *[check_port(port) for port in COMMON_PORTS],
        return_exceptions=True,
    )

    return sorted(open_ports)


async def _check_port(
    host: str, port: int, timeout: float
) -> bool:
    """Check if a TCP port is open on the host."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False


async def add_discovered_devices(
    db_client: Any,
    network_range: str,
    community: str = "public",
    timeout: float = 2.0,
    max_concurrent: int = 50,
    method: str = "all",
) -> dict[str, Any]:
    """
    Discover devices and add them to the database.

    Returns:
        Dict with 'found', 'added', 'scanned', and 'by_method' counts
    """
    import ipaddress

    # Count how many hosts we scanned
    try:
        network = ipaddress.ip_network(network_range, strict=False)
        scanned = network.num_addresses - 2  # Exclude network/broadcast
    except ValueError:
        scanned = 0  # Simple range; could count but not critical

    discovered = await discover_devices(
        network_range, community, timeout, max_concurrent, method
    )

    stats = {
        "scanned": scanned,
        "found": len(discovered),
        "added": 0,
        "by_method": {"snmp": 0, "ping": 0, "port": 0},
    }

    for device in discovered:
        method_used = device.get("discovery_method", "unknown")
        stats["by_method"][method_used] = stats["by_method"].get(method_used, 0) + 1

        # Check if device already exists
        existing = await db_client.get_device(device["ip_address"])
        if not existing:
            await db_client.create_device(
                {
                    "ip_address": device["ip_address"],
                    "community": device.get("community", community),
                    "sys_descr": device.get("sys_descr", ""),
                    "status": device.get("status", "discovered"),
                    "discovery_method": method_used,
                }
            )
            stats["added"] += 1

    return stats


def discover_devices_sync(
    network_range: str,
    community: str = "public",
    timeout: float = 1.0,
    max_concurrent: int = 50,
    method: str = "all",
) -> list[dict[str, Any]]:
    """Synchronous wrapper for discover_devices."""
    return asyncio.run(
        discover_devices(network_range, community, timeout, max_concurrent, method)
    )
