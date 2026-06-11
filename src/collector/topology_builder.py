#!/usr/bin/env python3
"""Topology builder - constructs network graph from SNMP data.

Includes device classification from sysDescr, BFS-based hierarchy
computation, subnet-based fallback grouping, and link deduplication.
"""

import ipaddress
import json
import re
from collections import defaultdict, deque
from typing import Any, Optional

import networkx as nx


_SYSDESCR_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("firewall", re.compile(r"asa|pfsense|fortigate|firepower|\bsrx\b|pan-os|opnsense|sonicwall|watchguard", re.I)),
    ("switch", re.compile(r"catalyst|c[23]\d{3}|c9\d{3}|nexus|\bex\d{3,4}|\bqfx\b|procurve|aruba.*switch|unifi.*switch|usw|netgear.*switch|dell.*switch|edgecos|dgs|tl-sg|cisco.*switch", re.I)),
    ("router", re.compile(r"\bisr\b|\bmx\d{2,3}\b|\bptx\b|vyos|edgeos|routeros|erx|erlite|udm|cisco.*router", re.I)),
    ("access_point", re.compile(r"aironet|unifi.*ap|\buap\b|wap|access.?point|meraki.*mr", re.I)),
    ("server", re.compile(r"linux|ubuntu|debian|centos|rhel|windows.*server|proxmox|esxi|vmware|synology|qnap|truenas", re.I)),
]

_NAME_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("firewall", re.compile(r"firewall|fw|pfsense|opnsense", re.I)),
    ("router", re.compile(r"router|gateway|gw|udm|erx", re.I)),
    ("switch", re.compile(r"switch|sw-|sw_|unifi.?switch|usw|\bcrs\b|mikrotik.*crs", re.I)),
    ("access_point", re.compile(r"ap[-_]|access.?point|uap", re.I)),
]

# Node types ranked by infrastructure likelihood (higher = more likely parent)
_INFRA_RANK: dict[str, int] = {
    "firewall": 5,
    "router": 4,
    "switch": 3,
    "access_point": 2,
    "server": 1,
    "host": 0,
    "end_device": 0,
}


def classify_device(sys_descr: Optional[str] = None, name: Optional[str] = None) -> str:
    """Classify a device from sysDescr and/or name. Returns node_type string."""
    if sys_descr:
        for node_type, pattern in _SYSDESCR_PATTERNS:
            if pattern.search(sys_descr):
                return node_type
    if name:
        for node_type, pattern in _NAME_PATTERNS:
            if pattern.search(name):
                return node_type
    return "host"


def _neighbor_count_role(neighbor_count: int) -> Optional[str]:
    """Infer role from LLDP neighbor count. More neighbors = more likely infra."""
    if neighbor_count >= 4:
        return "core"
    if neighbor_count >= 2:
        return "distribution"
    if neighbor_count == 1:
        return "access"
    return None


def _ip_sort_key(ip_str: str) -> tuple:
    """Sort key that puts gateway-like IPs first (.1, .254, .2)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        last_octet = int(ip_str.split(".")[-1])
        # .1 and .254 are most likely gateways, then .2, .3, etc.
        if last_octet == 1:
            priority = 0
        elif last_octet == 254:
            priority = 1
        elif last_octet == 2:
            priority = 2
        elif last_octet == 253:
            priority = 3
        else:
            priority = 10 + last_octet
        return (priority, ip)
    except (ValueError, IndexError):
        return (999, ip_str)


class TopologyBuilder:
    """Builds network topology from SNMP discovery data."""

    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.links: list[dict[str, Any]] = []
        self._link_set: set[str] = set()

    def add_node(self, node_id: str, label: str, **attributes) -> None:
        """Add a node to the topology."""
        self.nodes[node_id] = {
            "id": node_id,
            "label": label,
            **attributes,
        }

    def clear(self) -> None:
        """Clear all nodes and links."""
        self.nodes.clear()
        self.links.clear()
        self._link_set.clear()

    def add_link(
        self, source: str, target: str, source_port: str = "", target_port: str = ""
    ) -> None:
        """Add a link between two nodes. Deduplicates bidirectional links."""
        key = ":".join(sorted([source, target]))
        if key in self._link_set:
            existing = next(
                (l for l in self.links
                 if ":".join(sorted([l["source"], l["target"]])) == key),
                None,
            )
            if existing:
                if existing["source"] == source:
                    existing["source_port"] = existing["source_port"] or source_port
                    existing["target_port"] = existing["target_port"] or target_port
                else:
                    existing["target_port"] = existing["target_port"] or source_port
                    existing["source_port"] = existing["source_port"] or target_port
            return
        self._link_set.add(key)
        self.links.append(
            {
                "source": source,
                "target": target,
                "source_port": source_port,
                "target_port": target_port,
            }
        )

    def to_json(self) -> dict[str, list[dict[str, Any]]]:
        """Export topology as JSON."""
        return {
            "nodes": list(self.nodes.values()),
            "links": self.links,
        }

    def to_graph(self) -> nx.Graph:
        """Export topology as NetworkX graph."""
        G = nx.Graph()
        for node in self.nodes.values():
            attrs = {k: v for k, v in node.items() if k != "id"}
            G.add_node(node["id"], **attrs)
        for link in self.links:
            G.add_edge(
                link["source"],
                link["target"],
                source_port=link.get("source_port"),
                target_port=link.get("target_port"),
            )
        return G

    def compute_hierarchy(
        self,
        gateway_ip: Optional[str] = None,
        neighbor_counts: Optional[dict[str, int]] = None,
    ) -> None:
        """Compute hierarchy levels and parent_id via BFS + subnet fallback.

        Two-phase approach:
          Phase 1: BFS from root over LLDP links (if any exist).
          Phase 2: Subnet-based fallback for nodes unreachable by BFS
                   (no LLDP data). Groups by /24, picks subnet gateway,
                   assigns parent-child, creates synthetic links.

        Root selection priority:
          1. Explicit gateway_ip
          2. Node with highest degree centrality (most LLDP neighbors)
          3. Node with highest neighbor_count
          4. Subnet fallback: most infrastructure-like device in .1 subnet

        Levels: 0 = gateway/root, increasing = deeper in tree.
        Also assigns `role` (gateway, core, distribution, access, endpoint).
        """
        if not self.nodes:
            return

        neighbor_counts = neighbor_counts or {}
        graph = self.to_graph()
        if not graph.nodes:
            return

        # --- Root selection ---
        root = gateway_ip if gateway_ip and gateway_ip in self.nodes else None

        if root is None:
            best_score = -1
            for nid in self.nodes:
                degree = graph.degree(nid) if nid in graph else 0
                nc = neighbor_counts.get(nid, 0)
                score = degree * 10 + nc
                if score > best_score:
                    best_score = score
                    root = nid

        if root is None:
            root = next(iter(self.nodes))

        # --- Phase 1: BFS over LLDP links ---
        visited: dict[str, int] = {}
        parent_map: dict[str, Optional[str]] = {}
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        visited[root] = 0
        parent_map[root] = None

        while queue:
            current, level = queue.popleft()
            neighbors = list(graph.neighbors(current)) if current in graph else []
            for nb in neighbors:
                if nb not in visited:
                    visited[nb] = level + 1
                    parent_map[nb] = current
                    queue.append((nb, level + 1))

        # --- Phase 2: Subnet-based fallback for unvisited nodes ---
        unvisited = [nid for nid in self.nodes if nid not in visited]

        if unvisited:
            self._subnet_fallback(
                unvisited, root, visited, parent_map, neighbor_counts
            )

        # --- Assign level, parent_id, role to all nodes ---
        max_level = max(visited.values()) if visited else 0

        for nid, node in self.nodes.items():
            node["level"] = visited.get(nid, 99)
            node["parent_id"] = parent_map.get(nid)

            nc = neighbor_counts.get(nid, 0)
            role = _neighbor_count_role(nc)
            if nid == root:
                role = "gateway"
            elif role is None:
                node_type = node.get("node_type", "host")
                if node_type in ("router", "firewall"):
                    role = "core"
                elif node_type == "switch":
                    role = "distribution"
                elif node.get("parent_id") is None and nid != root:
                    role = "endpoint"
                else:
                    role = "endpoint"
            node["role"] = role

    def _subnet_fallback(
        self,
        unvisited: list[str],
        root: str,
        visited: dict[str, int],
        parent_map: dict[str, Optional[str]],
        neighbor_counts: dict[str, int],
    ) -> None:
        """Assign parent-child via /24 subnet grouping for nodes without LLDP.

        Algorithm:
          1. Group unvisited nodes by /24 subnet.
          2. For each subnet:
             a. If root (or a visited node) is in the same subnet,
                all unvisited nodes become direct children of that node.
             b. Otherwise, pick the best gateway candidate from unvisited
                members (IP .1/.254 preferred, higher infra rank wins ties).
                That gateway connects to root; remaining members are its children.
          3. Synthetic links are created for all parent→child edges so
             the DAG layout engine has edges to work with.
        """
        # Determine root's subnet
        root_subnet = None
        try:
            root_subnet = str(ipaddress.ip_network(f"{root}/24", strict=False))
        except ValueError:
            pass

        # Build map of subnet → visited nodes (to find bridge nodes)
        visited_subnets: dict[str, list[str]] = defaultdict(list)
        for vid in visited:
            try:
                vs = str(ipaddress.ip_network(f"{vid}/24", strict=False))
                visited_subnets[vs].append(vid)
            except ValueError:
                pass

        # Group unvisited by /24 subnet
        subnets: dict[str, list[str]] = defaultdict(list)
        for nid in unvisited:
            try:
                subnet = str(ipaddress.ip_network(f"{nid}/24", strict=False))
                subnets[subnet].append(nid)
            except ValueError:
                subnets["_non_ip"].append(nid)

        # Find max level so far to continue numbering
        max_level = max(visited.values()) if visited else 0

        for subnet, members in subnets.items():
            if not members or subnet == "_non_ip":
                continue

            # Check if root or any visited node is in this subnet
            if subnet == root_subnet:
                # Root is in this subnet — all members are direct children of root
                child_level = visited[root] + 1
                for child in members:
                    visited[child] = child_level
                    parent_map[child] = root
                    self.add_link(root, child, source_port="inferred", target_port="inferred")
                continue

            # Check for a visited bridge node in this subnet (e.g., a router)
            bridge_nodes = visited_subnets.get(subnet, [])
            if bridge_nodes:
                # Use the best bridge node as parent (prefer router/firewall)
                bridge = bridge_nodes[0]
                for bn in bridge_nodes:
                    if self.nodes.get(bn, {}).get("node_type") in ("router", "firewall"):
                        bridge = bn
                        break
                child_level = visited[bridge] + 1
                for child in members:
                    visited[child] = child_level
                    parent_map[child] = bridge
                    self.add_link(bridge, child, source_port="inferred", target_port="inferred")
                continue

            # No visited node in this subnet — pick a gateway from unvisited members
            def _gw_score(nid: str) -> tuple:
                sort_key = _ip_sort_key(nid)
                node = self.nodes.get(nid, {})
                infra = _INFRA_RANK.get(node.get("node_type", "host"), 0)
                nc = neighbor_counts.get(nid, 0)
                return (sort_key[0], -infra, -nc)

            members_sorted = sorted(members, key=_gw_score)
            subnet_gw = members_sorted[0]
            children = members_sorted[1:]

            # Subnet gateway connects to root (or a visited router as bridge)
            best_bridge = root
            for vid in visited:
                v_node = self.nodes.get(vid, {})
                if v_node.get("node_type") in ("router", "firewall"):
                    best_bridge = vid
                    break

            gw_level = visited[best_bridge] + 1
            visited[subnet_gw] = gw_level
            parent_map[subnet_gw] = best_bridge
            self.add_link(best_bridge, subnet_gw, source_port="inferred", target_port="inferred")

            child_level = gw_level + 1
            for child in children:
                visited[child] = child_level
                parent_map[child] = subnet_gw
                self.add_link(subnet_gw, child, source_port="inferred", target_port="inferred")

        # Handle non-IP nodes: attach to root
        child_level = visited[root] + 1
        for nid in subnets.get("_non_ip", []):
            visited[nid] = child_level
            parent_map[nid] = root
            self.add_link(root, nid, source_port="inferred", target_port="inferred")

    def export_json_file(self, filepath: str) -> None:
        """Export topology to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_json(), f, indent=2)
