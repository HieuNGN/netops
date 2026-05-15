#!/usr/bin/env python3
"""SNMP Discovery — v2c and v3 support."""

import argparse
import asyncio
from ipaddress import IPv4Address
from typing import Any, Optional

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    walk_cmd,
)

SNMP_TIMEOUT = 5
SNMP_RETRIES = 3


def _build_auth(device: dict[str, Any]) -> Any:
    version = device.get("snmp_version", "2c") or "2c"
    if version == "3":
        return UsmUserData(
            device.get("snmpv3_username", ""),
            authKey=device.get("snmpv3_auth_key"),
            authProtocol=device.get("snmpv3_auth_protocol") or None,
            privKey=device.get("snmpv3_priv_key"),
            privProtocol=device.get("snmpv3_priv_protocol") or None,
        )
    return CommunityData(device.get("community", "public"))


def _build_auth_v2(host: str, community: str = "public") -> Any:
    return CommunityData(community)


async def _get_async(host: str, auth_data: Any, oid: str, timeout: int = SNMP_TIMEOUT, retries: int = SNMP_RETRIES) -> tuple:
    return await get_cmd(
        SnmpEngine(),
        auth_data,
        UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
        ContextData(),
        ObjectIdentity(oid),
    )


async def _walk_async(host: str, auth_data: Any, oid: str, timeout: int = SNMP_TIMEOUT, retries: int = SNMP_RETRIES) -> tuple:
    return await walk_cmd(
        SnmpEngine(),
        auth_data,
        UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
        ContextData(),
        ObjectIdentity(oid),
    )


def get_sys_descr(host: str, community: str = "public") -> Optional[str]:
    return asyncio.run(get_sys_descr_async(host, _build_auth_v2(host, community)))


async def get_sys_descr_async(host: str, auth_data: Any) -> Optional[str]:
    error_indication, error_status, error_index, var_binds = await _get_async(
        host, auth_data, "1.3.6.1.2.1.1.1.0"
    )
    if error_indication or error_status:
        return None
    for var_bind in var_binds:
        return str(var_bind[1])
    return None


def _extract_lldp_index(oid_str: str) -> str:
    parts = oid_str.split(".")
    return parts[-1] if parts else ""


def walk_lldp_neighbors(host: str, community: str = "public") -> list[dict]:
    return asyncio.run(walk_lldp_neighbors_async(host, _build_auth_v2(host, community)))


async def walk_lldp_neighbors_async(host: str, auth_data: Any) -> list[dict]:
    port_error, _, _, port_var_binds = await _walk_async(
        host, auth_data, "1.0.8802.1.1.2.1.4.1.1"
    )
    sys_error, _, _, sys_var_binds = await _walk_async(
        host, auth_data, "1.0.8802.1.1.2.1.3.7.1.4"
    )

    port_map: dict[str, str] = {}
    if not port_error:
        for vb in port_var_binds:
            idx = _extract_lldp_index(str(vb[0]))
            port_map[idx] = str(vb[1])

    sys_map: dict[str, str] = {}
    if not sys_error:
        for vb in sys_var_binds:
            idx = _extract_lldp_index(str(vb[0]))
            sys_map[idx] = str(vb[1])

    neighbors = []
    for idx in port_map:
        neighbors.append({
            "local_port_index": idx,
            "neighbor_port": port_map[idx],
            "neighbor_name": sys_map.get(idx, "unknown"),
        })
    return neighbors


async def poll_device_async(device: dict[str, Any], timeout: int = SNMP_TIMEOUT, retries: int = SNMP_RETRIES) -> dict[str, Any]:
    auth = _build_auth(device)
    sys_descr = await get_sys_descr_async(device["ip_address"], auth)
    neighbors = await walk_lldp_neighbors_async(device["ip_address"], auth)
    return {"sys_descr": sys_descr, "neighbors": neighbors, "success": sys_descr is not None}


def main():
    parser = argparse.ArgumentParser(description="SNMP Discovery Tool")
    parser.add_argument("host", help="SNMP host IP address")
    parser.add_argument("-c", "--community", default="public", help="SNMP community")
    parser.add_argument("--action", choices=["sysdescr", "lldp", "all"], default="all")

    args = parser.parse_args()

    try:
        IPv4Address(args.host)
    except ValueError:
        print(f"Invalid IP address: {args.host}")
        return 1

    auth = _build_auth_v2(args.host, args.community)

    if args.action in ["sysdescr", "all"]:
        print("\n=== System Description ===")
        descr = asyncio.get_event_loop().run_until_complete(
            get_sys_descr_async(args.host, auth)
        )
        if descr:
            print(f"sysDescr: {descr}")

    if args.action in ["lldp", "all"]:
        print("\n=== LLDP Neighbor Map ===")
        neighbors = asyncio.get_event_loop().run_until_complete(
            walk_lldp_neighbors_async(args.host, auth)
        )
        for n in neighbors:
            print(f"  Index {n['local_port_index']}: {n['neighbor_name']} via {n['neighbor_port']}")

    return 0


if __name__ == "__main__":
    exit(main())
