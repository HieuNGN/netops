#!/usr/bin/env python3
"""SNMP Discovery Spike - Verify SNMP connectivity and walk LLDP tables."""

import argparse
from ipaddress import IPv4Address
from typing import Optional

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    walkCmd,
)


def get_sys_descr(host: str, community: str = "public") -> Optional[str]:
    """Get system description (sysDescr) from device."""
    error_indication, error_status, error_index, var_binds = next(
        getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=0),
            UdpTransportTarget((host, 161), timeout=5, retries=3),
            ContextData(),
            ObjectIdentity("1.3.6.1.2.1.1.1.0"),  # sysDescr
        )
    )

    if error_indication:
        print(f"Error: {error_indication}")
        return None
    elif error_status:
        print(f"Error status: {error_status.prettyPrint()}")
        return None

    for var_bind in var_binds:
        return str(var_bind[1])

    return None


def walk_lldp_rem_port_id(host: str, community: str = "public") -> dict:
    """Walk LLDP remote port ID (lldpRemPortId)."""
    result = {}
    error_indication, error_status, error_index, var_binds = next(
        walkCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=0),
            UdpTransportTarget((host, 161), timeout=5, retries=3),
            ContextData(),
            ObjectIdentity("1.0.8802.1.1.2.1.4.1.1"),  # lldpRemPortId
        )
    )

    if error_indication:
        print(f"Error walking LLDP: {error_indication}")
        return result

    for var_bind in var_binds:
        # Extract the OID index (last number in the OID)
        oid_str = str(var_bind[0])
        port_id = str(var_bind[1])
        result[oid_str] = port_id

    return result


def _extract_lldp_index(oid_str: str) -> str:
    """Extract the LLDP entry index from OID.

    LLDP OIDs follow pattern: ...!lldpRemTable.lldpRemEntry.lldpRemSysName.oid_index
    The last numeric part is the index that correlates different LLDP columns.
    """
    parts = oid_str.split(".")
    return parts[-1] if parts else ""


def walk_lldp_neighbors(host: str, community: str = "public") -> list[dict]:
    """Walk LLDP tables and correlate neighbors with local ports.

    Returns a list of neighbor relationships with:
    - local_port: The local interface port name
    - neighbor_name: The remote system name
    - neighbor_port: The remote port identifier
    """
    # lldpRemPortId - Remote port identifier
    port_result = {}
    error_indication, error_status, error_index, var_binds = next(
        walkCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=0),
            UdpTransportTarget((host, 161), timeout=5, retries=3),
            ContextData(),
            ObjectIdentity("1.0.8802.1.1.2.1.4.1.1"),  # lldpRemPortId
        )
    )

    if error_indication:
        print(f"Error walking LLDP: {error_indication}")
        return []

    for var_bind in var_binds:
        idx = _extract_lldp_index(str(var_bind[0]))
        port_result[idx] = str(var_bind[1])

    # lldpRemSysName - Remote system name
    sys_result = {}
    error_indication, error_status, error_index, var_binds = next(
        walkCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=0),
            UdpTransportTarget((host, 161), timeout=5, retries=3),
            ContextData(),
            ObjectIdentity("1.0.8802.1.1.2.1.3.7.1.4"),  # lldpRemSysName
        )
    )

    if error_indication:
        print(f"Error walking LLDP: {error_indication}")
        return []

    for var_bind in var_binds:
        idx = _extract_lldp_index(str(var_bind[0]))
        sys_result[idx] = str(var_bind[1])

    # Correlate port and system name using the common index
    neighbors = []
    for idx in port_result:
        neighbors.append({
            "local_port_index": idx,
            "neighbor_port": port_result[idx],
            "neighbor_name": sys_result.get(idx, "unknown"),
        })

    return neighbors


def main():
    parser = argparse.ArgumentParser(description="SNMP Discovery Tool")
    parser.add_argument("host", help="SNMP host IP address")
    parser.add_argument(
        "-c", "--community", default="public", help="SNMP community (default: public)"
    )
    parser.add_argument(
        "--action",
        choices=["sysdescr", "lldp", "all"],
        default="all",
        help="Action to perform",
    )

    args = parser.parse_args()

    try:
        IPv4Address(args.host)
    except ValueError:
        print(f"Invalid IP address: {args.host}")
        return 1

    if args.action in ["sysdescr", "all"]:
        print(f"\n=== System Description ===")
        sys_descr = get_sys_descr(args.host, args.community)
        if sys_descr:
            print(f"sysDescr: {sys_descr}")

    if args.action in ["lldp", "all"]:
        print(f"\n=== LLDP Neighbor Map ===")
        neighbors = map_lldp_neighbors(args.host, args.community)
        for local_port, neighbor in neighbors.items():
            print(f"  {local_port} -> {neighbor['system_name']} ({neighbor['port_id']})")

    return 0


if __name__ == "__main__":
    exit(main())
