"""Network device discovery - scans IP ranges for responsive devices via SNMP, ping, or TCP ports."""

import asyncio
import datetime
import platform
import socket
from typing import Any, Optional

from .spike_snmp import get_sys_descr
from .topology_builder import classify_device

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
    device_found_event_emitter: Optional[Any] = None,
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

    # Defense-in-depth: refuse to expand a CIDR larger than the
    # public-API cap (4096 hosts). Prevents accidental DoS if a
    # caller forgets the upstream check.
    _MAX_HOSTS = 4096
    try:
        network = ipaddress.ip_network(network_range, strict=False)
        if network.num_addresses > _MAX_HOSTS:
            return []
        hosts = [str(host) for host in network.hosts()]
        return await _scan_hosts(hosts, community, timeout, max_concurrent, method, device_found_event_emitter)
    except ValueError:
        pass

    return await _discover_range(network_range, community, timeout, max_concurrent, method, device_found_event_emitter)


async def _discover_range(
    range_str: str,
    community: str,
    timeout: float,
    max_concurrent: int,
    method: str,
    device_found_event_emitter: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Discover devices in a simple IP range like 192.168.1.1-100."""
    parts = range_str.split("-")
    if len(parts) != 2:
        return []

    base_parts = parts[0].rsplit(".", 1)
    if len(base_parts) != 2:
        return []

    base_prefix = base_parts[0]
    try:
        start = int(base_parts[1])
        end = int(parts[1])
    except ValueError:
        return []

    if end < start:
        return []
    # Cap the range to prevent DoS via huge ranges. Mirrors the
    # /api/discover* size guard (4096 hosts).
    if end - start + 1 > 4096:
        return []

    hosts = [f"{base_prefix}.{i}" for i in range(start, end + 1)]
    return await _scan_hosts(hosts, community, timeout, max_concurrent, method, device_found_event_emitter)


async def _scan_hosts(
    hosts: list[str],
    community: str,
    timeout: float,
    max_concurrent: int,
    method: str,
    device_found_event_emitter: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Scan a list of hosts using the specified discovery method."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[dict[str, Any]] = []

    async def scan_host(host: str) -> Optional[dict[str, Any]]:
        async with semaphore:
            device = await _probe_host(host, community, timeout, method)
            if device:
                results.append(device)
                # Emit real-time event immediately on discovery
                if device_found_event_emitter is not None:
                    try:
                        method_used = device.get("discovery_method", "unknown")
                        await device_found_event_emitter({
                            "type": "device_found",
                            "ip_address": device["ip_address"],
                            "method": method_used,
                            "sys_descr": device.get("sys_descr", ""),
                            "is_new": True,  # Will be reconciled later by caller
                            "total": len(results),  # Running count for UI progress
                        })
                    except Exception:
                        pass
            return device

    # Batch hosts to cap total concurrent asyncio tasks and smooth CPU curve
    BATCH_SIZE = 20
    for i in range(0, len(hosts), BATCH_SIZE):
        batch = hosts[i : i + BATCH_SIZE]
        await asyncio.gather(
            *[scan_host(host) for host in batch],
            return_exceptions=True
        )
        # Yield between batches to prevent CPU spikes
        if i + BATCH_SIZE < len(hosts):
            await asyncio.sleep(0.05)

    return results


async def _probe_host(
    host: str, community: str, timeout: float, method: str
) -> Optional[dict[str, Any]]:
    """Probe a single host using the requested discovery method(s)."""
    snmp_result = None
    ping_alive = False
    open_ports: list[int] = []

    # Fast pre-check: skip SNMP/port scan if host doesn't respond to ping
    ping_alive = await _probe_ping(host, timeout)
    if not ping_alive:
        return None  # host down — nothing to discover

    # SNMP discovery (only on hosts that are alive)
    if method in ("snmp", "all"):
        snmp_result = await _probe_snmp(host, community, timeout)
        if snmp_result:
            snmp_result["discovery_method"] = "snmp"
            return snmp_result

    # TCP port scan for non-SNMP alive hosts
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
            "status": "online",
        }

    return None


async def _probe_snmp(
    host: str, community: str, timeout: float
) -> Optional[dict[str, Any]]:
    """Probe a single host via SNMP."""
    loop = asyncio.get_event_loop()
    try:
        sys_descr = await asyncio.wait_for(
            loop.run_in_executor(None, get_sys_descr, host, community),
            timeout=timeout,  # use caller timeout directly (fast fail)
        )
        if sys_descr:
            return {
                "ip_address": host,
                "sys_descr": sys_descr,
                "community": community,
                "discovery_method": "snmp",
                "open_ports": [161],
                "status": "online",
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
    device_found_event_emitter: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Discover devices and add them to the database.

    Raises:
        ValueError: if network_range expands to more than 4096 hosts.

    Returns:
        Dict with 'found', 'added', 'scanned', and 'by_method' counts
    """
    import ipaddress

    # Defense-in-depth: enforce the 4096-host cap at this layer too.
    # /api/discover* checks first, but internal callers (e.g.
    # _startup_auto_discover, scripts) might not. Mirrors the
    # CIDR guard in discover_devices().
    try:
        network = ipaddress.ip_network(network_range, strict=False)
        if network.num_addresses > 4096:
            raise ValueError(
                f"network_range too large ({network.num_addresses} addresses); "
                "max 4096 hosts per scan (use a smaller CIDR)"
            )
        scanned = network.num_addresses - 2  # Exclude network/broadcast
    except ValueError as ve:
        if "too large" in str(ve):
            raise
        scanned = 0  # Simple range; could count but not critical

    discovered = await discover_devices(
        network_range, community, timeout, max_concurrent, method,
        device_found_event_emitter=device_found_event_emitter,
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
        sys_descr = device.get("sys_descr", "")
        node_type = classify_device(sys_descr=sys_descr, name=device.get("name", ""))

        # Check if device already exists
        existing = await db_client.get_device(device["ip_address"])
        if not existing:
            await db_client.create_device(
                {
                    "ip_address": device["ip_address"],
                    "community": device.get("community", community),
                    "sys_descr": sys_descr,
                    "node_type": node_type,
                    "status": device.get("status", "online"),
                    "discovery_method": method_used,
                }
            )
            stats["added"] += 1
        else:
            await db_client.update_device(existing["id"], {
                "status": "online",
                "sys_descr": sys_descr or existing.get("sys_descr", ""),
                "node_type": node_type,
                "discovery_method": method_used,
            })
            stats["updated"] += 1

    return stats


async def rescan_and_replace(
    db_client: Any,
    network_range: str,
    community: str = "public",
    timeout: float = 2.0,
    max_concurrent: int = 50,
    method: str = "all",
    device_found_event_emitter: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Nuke every device + topology, then rediscover from the given range.

    Returns:
        Dict with 'cleared', 'found', 'added', 'scanned', 'by_method'
    """
    cleared = 0
    try:
        cleared = await db_client.clear_all_devices()
    except AttributeError:
        # Backend lacks the helper; fall back to per-row delete
        existing = await db_client.list_devices()
        ids = [d.get("id") or d.get("ip_address") for d in existing if d]
        cleared = await db_client.bulk_delete_devices(ids) if ids else 0

    stats = await add_discovered_devices(
        db_client, network_range, community, timeout, max_concurrent, method,
        device_found_event_emitter=device_found_event_emitter,
    )
    stats["cleared"] = cleared
    return stats


# ---------------------------------------------------------------------------
# Phase 1: non-destructive merge-based discovery.
# Replaces the destructive rescan_and_replace as the default path.
# Preserves manual devices, marks missing auto devices offline, and
# emits device_stale events for devices offline >= 72h.
# ---------------------------------------------------------------------------

_STALE_THRESHOLD_HOURS = 72


async def rescan_and_merge(
    db_client: Any,
    network_range: str,
    community: str = "public",
    timeout: float = 2.0,
    max_concurrent: int = 50,
    method: str = "all",
    preserve_manual: bool = True,
    stale_event_emitter: Optional[Any] = None,
    device_found_event_emitter: Optional[Any] = None,
) -> dict[str, Any]:
    """Phase 1 merge-based discovery.

    Algorithm:
      1. Run probe on the network range. Get fresh set of IPs.
      2. For each discovered device:
         - IP exists in DB -> update_device (status=online, refresh
           sys_descr, last_scanned=now, clear offline_since).
         - IP is new         -> create_device with discovery_method
           from the probe.
      3. For each current device NOT in the fresh set:
         - discovery_method == "manual" and preserve_manual -> skip.
         - status != "offline" -> mark offline + set offline_since=now.
         - status == "offline" and hours_since(offline_since) >= 72
           -> emit "device_stale" event (caller is expected to fan
           this out to SSE subscribers; the function only calls the
           optional emitter if provided).

    Returns dict with scanned, found, added, updated, preserved,
    marked_offline, stale, by_method.
    """
    import datetime as _dt

    # 1. probe the range
    discovered = await discover_devices(
        network_range, community, timeout, max_concurrent, method,
        device_found_event_emitter=device_found_event_emitter,
    )
    discovered_ips = {d["ip_address"] for d in discovered}

    # 2. existing devices in DB (across the whole DB; the merge is
    # not range-scoped because devices outside the range may still
    # be tracked manually)
    current = await db_client.list_devices()
    current_by_ip = {d["ip_address"]: d for d in current if d.get("ip_address")}

    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()

    stats = {
        "scanned": 0,
        "found": len(discovered),
        "added": 0,
        "updated": 0,
        "preserved": 0,
        "marked_offline": 0,
        "stale": 0,
        "by_method": {"snmp": 0, "ping": 0, "port": 0},
    }

    # Try to derive scanned count from CIDR (best effort)
    try:
        import ipaddress as _ip
        net = _ip.ip_network(network_range, strict=False)
        stats["scanned"] = net.num_addresses - 2
    except ValueError:
        pass

    # 3a. upsert discovered
    for dev in discovered:
        ip = dev["ip_address"]
        method_used = dev.get("discovery_method", "snmp")
        sys_descr = dev.get("sys_descr", "")
        node_type = classify_device(sys_descr=sys_descr, name=dev.get("name", ""))
        stats["by_method"][method_used] = stats["by_method"].get(method_used, 0) + 1
        existing = current_by_ip.get(ip)
        if existing:
            update_data = {
                "status": "online",
                "sys_descr": sys_descr or existing.get("sys_descr", ""),
                "node_type": node_type,
                "last_scanned": now_iso,
                "discovery_method": method_used,
            }
            # Clear offline_since on a re-sighted device
            update_data["offline_since"] = None
            try:
                await db_client.update_device(existing["id"], update_data)
            except Exception:
                # Some backends may not have offline_since; ignore
                update_data.pop("offline_since", None)
                await db_client.update_device(existing["id"], update_data)
            stats["updated"] += 1
        else:
            await db_client.create_device({
                "ip_address": ip,
                "community": dev.get("community", community),
                "sys_descr": sys_descr,
                "node_type": node_type,
                "status": "online",
                "discovery_method": method_used,
            })
            stats["added"] += 1

    # 3b. mark missing devices offline (skip manual if preserve_manual)
    for ip, dev in current_by_ip.items():
        if ip in discovered_ips:
            continue
        if dev.get("status") == "unknown":
            # never-was-seen devices outside this range; leave alone
            continue
        if preserve_manual and dev.get("discovery_method") == "manual":
            stats["preserved"] += 1
            continue
        if dev.get("status") == "offline":
            # check stale threshold
            offline_since = dev.get("offline_since")
            if offline_since and _is_stale(offline_since):
                stats["stale"] += 1
                if stale_event_emitter is not None:
                    try:
                        await stale_event_emitter({
                            "type": "device_stale",
                            "device_id": dev.get("id") or ip,
                            "ip_address": ip,
                            "name": dev.get("name", ""),
                            "offline_since": offline_since,
                            "offline_hours": _hours_since(offline_since),
                        })
                    except Exception:
                        pass
            continue
        # mark offline + set offline_since
        try:
            await db_client.update_device(
                dev.get("id") or ip,
                {"status": "offline", "offline_since": now_iso},
            )
        except Exception:
            # Backend may not support offline_since
            await db_client.update_device(
                dev.get("id") or ip,
                {"status": "offline"},
            )
        stats["marked_offline"] += 1

    return stats


def _parse_iso_dt(s: str) -> Optional["datetime.datetime"]:
    if not s:
        return None
    try:
        # Accept "Z" suffix and naive ISO
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _hours_since(iso_str: str) -> float:
    """Return hours between iso_str and now (UTC). Negative if future."""
    dt = _parse_iso_dt(iso_str)
    if dt is None:
        return 0.0
    now = datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (now - dt).total_seconds() / 3600.0


def _is_stale(iso_str: str) -> bool:
    return _hours_since(iso_str) >= _STALE_THRESHOLD_HOURS


def expand_cidr_hosts(network_range: str, limit: int = 1024) -> list[str]:
    """Expand a CIDR or dotted range into a list of host strings (capped)."""
    import ipaddress

    try:
        network = ipaddress.ip_network(network_range, strict=False)
        return [str(h) for h in network.hosts()][:limit]
    except ValueError:
        pass

    if "-" in network_range:
        parts = network_range.split("-")
        if len(parts) == 2:
            base_parts = parts[0].rsplit(".", 1)
            if len(base_parts) == 2:
                try:
                    start = int(base_parts[1])
                    end = int(parts[1])
                    return [
                        f"{base_parts[0]}.{i}"
                        for i in range(start, min(end, start + limit) + 1)
                    ]
                except ValueError:
                    return []
    return []


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
