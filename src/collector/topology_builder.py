#!/usr/bin/env python3
"""Topology builder - constructs network graph from SNMP data."""

import json
from typing import Any

import networkx as nx


class TopologyBuilder:
    """Builds network topology from SNMP discovery data."""

    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.links: list[dict[str, Any]] = []

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

    def add_link(
        self, source: str, target: str, source_port: str = "", target_port: str = ""
    ) -> None:
        """Add a link between two nodes."""
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
            G.add_node(node["id"], label=node.get("label"), **node)
        for link in self.links:
            G.add_edge(
                link["source"],
                link["target"],
                source_port=link.get("source_port"),
                target_port=link.get("target_port"),
            )
        return G

    def export_json_file(self, filepath: str) -> None:
        """Export topology to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_json(), f, indent=2)
