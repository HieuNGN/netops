"""Detect the host machine's primary network: IP, CIDR, hostname, gateway."""

import asyncio
import ipaddress
import platform
import re
import socket
from typing import Optional


async def detect_host_network() -> dict[str, Optional[str]]:
    """Return host_ip, cidr, hostname, gateway for the default-route interface.

    Falls back gracefully on unsupported platforms or missing tools.
    """
    system = platform.system().lower()
    hostname = socket.gethostname() or "Current Device"

    if system == "linux":
        return await _detect_linux(hostname)
    if system == "darwin":
        return await _detect_macos(hostname)
    # Windows / other — best-effort socket probe
    return _detect_fallback(hostname)


async def _detect_linux(hostname: str) -> dict[str, Optional[str]]:
    host_ip = gateway = interface = None
    cidr = "192.168.1.0/24"  # sensible default

    # Parse default route: "default via G.W dev IFACE proto ... src HOST_IP ..."
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "route", "show", "default",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        line = stdout.decode().strip()
        if line:
            gw_m = re.search(r"via\s+(\S+)", line)
            dev_m = re.search(r"dev\s+(\S+)", line)
            src_m = re.search(r"src\s+(\S+)", line)
            gateway = gw_m.group(1) if gw_m else None
            interface = dev_m.group(1) if dev_m else None
            host_ip = src_m.group(1) if src_m else None
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        pass

    # If we have the interface, get its CIDR from `ip addr show dev IFACE`
    if interface:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "-4", "addr", "show", "dev", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            inet_m = re.search(r"inet\s+(\S+)", stdout.decode())
            if inet_m:
                cidr = inet_m.group(1)  # e.g. "192.168.2.202/24"
                if not host_ip:
                    host_ip = str(ipaddress.ip_network(cidr, strict=False).network_address)
        except (asyncio.TimeoutError, FileNotFoundError, OSError, ValueError):
            pass
    elif host_ip:
        # Guess /24 from the host IP
        try:
            net = ipaddress.ip_network(f"{host_ip}/24", strict=False)
            cidr = str(net)
        except ValueError:
            pass

    return {
        "host_ip": host_ip,
        "cidr": cidr,
        "hostname": hostname,
        "gateway": gateway,
        "interface": interface,
    }


async def _detect_macos(hostname: str) -> dict[str, Optional[str]]:
    gateway = interface = None
    host_ip = None
    cidr = "192.168.1.0/24"

    try:
        proc = await asyncio.create_subprocess_exec(
            "route", "-n", "get", "default",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        text = stdout.decode()
        gw_m = re.search(r"gateway:\s+(\S+)", text)
        if_m = re.search(r"interface:\s+(\S+)", text)
        gateway = gw_m.group(1) if gw_m else None
        interface = if_m.group(1) if if_m else None
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        pass

    if interface:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ifconfig", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            text = stdout.decode()
            inet_m = re.search(r"inet\s+(\S+)", text)
            if inet_m:
                cidr = inet_m.group(1)
                if not host_ip:
                    host_ip = str(ipaddress.ip_network(cidr, strict=False).network_address)
        except (asyncio.TimeoutError, FileNotFoundError, OSError, ValueError):
            pass

    return {
        "host_ip": host_ip,
        "cidr": cidr,
        "hostname": hostname,
        "gateway": gateway,
        "interface": interface,
    }


def _detect_fallback(hostname: str) -> dict[str, Optional[str]]:
    host_ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host_ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass

    cidr = "192.168.1.0/24"
    if host_ip:
        try:
            net = ipaddress.ip_network(f"{host_ip}/24", strict=False)
            cidr = str(net)
        except ValueError:
            pass

    return {
        "host_ip": host_ip,
        "cidr": cidr,
        "hostname": hostname,
        "gateway": None,
        "interface": None,
    }