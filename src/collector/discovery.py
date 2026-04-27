"""Network device discovery - scans IP ranges for SNMP-responsive devices."""

import asyncio
import socket
from typing import Any, Optional

from .spike_snmp import get_sys_descr


async def discover_devices(
    network_range: str,
    community: str = "public",
    timeout: float = 1.0,
    max_concurrent: int = 50,
) -> list[dict[str, str]]:
    """
    Discover SNMP-responsive devices in a network range.

    Args:
        network_range: CIDR notation (e.g., "192.168.1.0/24") or IP range
        community: SNMP community string
        timeout: Timeout per host in seconds
        max_concurrent: Maximum concurrent probes

    Returns:
        List of discovered devices with ip_address, sys_descr fields
    """
    import ipaddress

    # Parse network range
    try:
        network = ipaddress.ip_network(network_range, strict=False)
    except ValueError:
        # Try parsing as simple range (e.g., "192.168.1.1-100")
        return await _discover_range(network_range, community, timeout, max_concurrent)

    # Generate host list (exclude network and broadcast addresses)
    hosts = [
        str(host)
        for host in network.hosts()
    ]

    return await _scan_hosts(hosts, community, timeout, max_concurrent)


async def _discover_range(
    range_str: str,
    community: str,
    timeout: float,
    max_concurrent: int,
) -> list[dict[str, str]]:
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
    return await _scan_hosts(hosts, community, timeout, max_concurrent)


async def _scan_hosts(
    hosts: list[str],
    community: str,
    timeout: float,
    max_concurrent: int,
) -> list[dict[str, str]]:
    """Scan a list of hosts for SNMP responsiveness."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def scan_host(host: str) -> Optional[dict[str, str]]:
        async with semaphore:
            device = await _probe_host(host, community, timeout)
            if device:
                results.append(device)
            return device

    # Use asyncio.gather with return_exceptions to handle failures
    await asyncio.gather(
        *[scan_host(host) for host in hosts],
        return_exceptions=True
    )

    return results


async def _probe_host(
    host: str, community: str, timeout: float
) -> Optional[dict[str, str]]:
    """Probe a single host for SNMP response."""

    # First check if port 161 is open (quick TCP check)
    port_open = await _check_port(host, 161, timeout)
    if not port_open:
        return None

    # Then try SNMP query
    loop = asyncio.get_event_loop()
    try:
        sys_descr = await asyncio.wait_for(
            loop.run_in_executor(None, get_sys_descr, host, community),
            timeout=timeout * 2,  # SNMP query might take longer
        )

        if sys_descr:
            return {
                "ip_address": host,
                "sys_descr": sys_descr,
                "community": community,
            }
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass

    return None


async def _check_port(
    host: str, port: int, timeout: float
) -> bool:
    """Check if a TCP port is open on the host."""

    async def _connect() -> bool:
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

    return await _connect()


def discover_devices_sync(
    network_range: str,
    community: str = "public",
    timeout: float = 1.0,
    max_concurrent: int = 50,
) -> list[dict[str, str]]:
    """Synchronous wrapper for discover_devices."""
    return asyncio.run(
        discover_devices(network_range, community, timeout, max_concurrent)
    )


async def add_discovered_devices(
    db_client: Any,
    network_range: str,
    community: str = "public",
    timeout: float = 2.0,
    max_concurrent: int = 50,
) -> dict[str, int]:
    """
    Discover devices and add them to the database.

    Returns:
        Dict with 'found' and 'added' counts
    """
    discovered = await discover_devices(
        network_range, community, timeout, max_concurrent
    )

    stats = {"found": len(discovered), "added": 0}

    for device in discovered:
        # Check if device already exists
        existing = db_client.get_device(device["ip_address"])
        if not existing:
            db_client.create_device(
                {
                    "ip_address": device["ip_address"],
                    "community": device.get("community", community),
                    "sys_descr": device.get("sys_descr", ""),
                    "status": "unknown",
                }
            )
            stats["added"] += 1

    return stats


