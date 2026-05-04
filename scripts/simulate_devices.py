#!/usr/bin/env python3
"""Add simulated devices and topology data for demo/testing."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.sqlite_client import AsyncSQLiteClient

SIMULATED_DEVICES = [
    {"name": "Core-Router-1", "ip_address": "192.168.1.1", "community": "public"},
    {"name": "Core-Router-2", "ip_address": "192.168.1.2", "community": "public"},
    {"name": "Distribution-SW-1", "ip_address": "192.168.1.10", "community": "public"},
    {"name": "Distribution-SW-2", "ip_address": "192.168.1.11", "community": "public"},
    {"name": "Access-SW-1", "ip_address": "192.168.1.100", "community": "public"},
    {"name": "Access-SW-2", "ip_address": "192.168.1.101", "community": "public"},
    {"name": "Access-SW-3", "ip_address": "192.168.1.102", "community": "public"},
    {"name": "Firewall-1", "ip_address": "192.168.1.254", "community": "public"},
]

# Topology links: (source_ip, target_ip, source_port, target_port)
SIMULATED_LINKS = [
    ("192.168.1.254", "192.168.1.1", "eth0", "ge-0/0/0"),  # Firewall -> Core-Router-1
    ("192.168.1.254", "192.168.1.2", "eth1", "ge-0/0/0"),  # Firewall -> Core-Router-2
    ("192.168.1.1", "192.168.1.2", "ge-0/0/1", "ge-0/0/1"),  # Core-Router-1 <-> Core-Router-2
    ("192.168.1.1", "192.168.1.10", "ge-0/0/2", "xe-0/0/1"),  # Core-Router-1 -> Dist-SW-1
    ("192.168.1.2", "192.168.1.11", "ge-0/0/2", "xe-0/0/1"),  # Core-Router-2 -> Dist-SW-2
    ("192.168.1.10", "192.168.1.100", "ge-0/0/1", "ge-0/0/1"),  # Dist-SW-1 -> Access-SW-1
    ("192.168.1.10", "192.168.1.101", "ge-0/0/2", "ge-0/0/1"),  # Dist-SW-1 -> Access-SW-2
    ("192.168.1.11", "192.168.1.102", "ge-0/0/1", "ge-0/0/1"),  # Dist-SW-2 -> Access-SW-3
]


async def simulate_devices():
    """Create simulated devices and topology."""
    db = AsyncSQLiteClient()
    await db.connect()
    await db.init_db()

    # Clear existing topology and devices for clean demo
    print("Clearing existing data...")
    cursor = await db._db.execute("DELETE FROM topology_links")
    await db._db.commit()
    cursor = await db._db.execute("DELETE FROM topology_nodes")
    await db._db.commit()
    cursor = await db._db.execute("DELETE FROM devices")
    await db._db.commit()

    print("Creating simulated devices...")
    devices = {}
    for device_data in SIMULATED_DEVICES:
        device = await db.create_device(device_data)
        devices[device_data["ip_address"]] = device
        print(f"  Created: {device['name']} ({device['ip_address']})")

    print("\nCreating topology nodes...")
    nodes = []
    for ip, device in devices.items():
        node = {
            "id": ip,
            "device_id": device["id"],
            "label": device["name"],
            "node_type": "router" if "Router" in device["name"] else
                        "firewall" if "Firewall" in device["name"] else
                        "switch",
            "status": "online",
        }
        nodes.append(node)

    print("\nCreating topology links...")
    links = []
    for src_ip, tgt_ip, src_port, tgt_port in SIMULATED_LINKS:
        link = {
            "id": f"{src_ip}-{tgt_ip}",
            "source": src_ip,
            "target": tgt_ip,
            "source_port": src_port,
            "target_port": tgt_port,
            "status": "active",
        }
        links.append(link)

    # Upsert topology
    changes = await db.upsert_topology(nodes, links)
    print(f"\nTopology created:")
    print(f"  Nodes: {changes['nodes_added']} added")
    print(f"  Links: {changes['links_added']} added")

    # Update device status to online
    print("\nUpdating device status to online...")
    for ip, device in devices.items():
        await db.update_device(device["id"], {"status": "online", "sys_descr": f"Simulated {device['name']}"})

    await db.close()
    print("\nSimulation complete! Refresh the topology page to see the network graph.")


if __name__ == "__main__":
    asyncio.run(simulate_devices())
