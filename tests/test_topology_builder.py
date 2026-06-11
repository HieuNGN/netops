"""Tests for TopologyBuilder: classification, hierarchy, link dedup."""

import pytest
from src.collector.topology_builder import TopologyBuilder, classify_device


class TestClassifyDevice:
    def test_cisco_switch(self):
        assert classify_device("Cisco IOS Software, C3750 Software") == "switch"

    def test_cisco_router(self):
        assert classify_device("Cisco IOS Software, ISR Software") == "router"

    def test_pfsense_firewall(self):
        assert classify_device("pfSense 2.7.0-RELEASE amd64") == "firewall"

    def test_linux_server(self):
        assert classify_device("Linux proxmox 6.1.0 #1 SMP") == "server"

    def test_unifi_ap(self):
        assert classify_device("UniFi AP AC Pro") == "access_point"

    def test_name_fallback_router(self):
        assert classify_device(name="gateway-router") == "router"

    def test_name_fallback_switch(self):
        assert classify_device(name="sw-core-01") == "switch"

    def test_name_fallback_firewall(self):
        assert classify_device(name="pfsense-fw") == "firewall"

    def test_unknown_defaults_host(self):
        assert classify_device("some random string") == "host"

    def test_none_inputs(self):
        assert classify_device() == "host"

    def test_juniper_switch(self):
        assert classify_device("Juniper Networks, Inc. ex4300-48t") == "switch"

    def test_juniper_router(self):
        assert classify_device("Juniper Networks, Inc. mx240") == "router"

    def test_mikrotik_router(self):
        assert classify_device("MikroTik RouterOS 7.12 CCR1009") == "router"

    def test_synology_server(self):
        assert classify_device("Linux DiskStation 4.4.302+ #123") == "server"

    def test_sysdescr_beats_name(self):
        assert classify_device("Cisco IOS C3750", name="my-router") == "switch"


class TestLinkDedup:
    def test_no_duplicate_bidirectional(self):
        b = TopologyBuilder()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_link("A", "B", "eth0", "ge-0/0/0")
        b.add_link("B", "A", "ge-0/0/0", "eth0")
        assert len(b.links) == 1

    def test_ports_merged_on_dedup(self):
        b = TopologyBuilder()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_link("A", "B", "eth0", "")
        b.add_link("B", "A", "ge-0/0/0", "")
        assert len(b.links) == 1
        link = b.links[0]
        assert link["source_port"] == "eth0"
        assert link["target_port"] == "ge-0/0/0"

    def test_same_direction_no_dup(self):
        b = TopologyBuilder()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_link("A", "B", "eth0", "ge-0/0/0")
        b.add_link("A", "B", "eth1", "ge-0/0/1")
        assert len(b.links) == 1

    def test_different_pairs_not_deduped(self):
        b = TopologyBuilder()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_node("C", "C")
        b.add_link("A", "B")
        b.add_link("A", "C")
        assert len(b.links) == 2

    def test_clear_resets_link_set(self):
        b = TopologyBuilder()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_link("A", "B")
        assert len(b.links) == 1
        b.clear()
        b.add_node("A", "A")
        b.add_node("B", "B")
        b.add_link("A", "B")
        assert len(b.links) == 1


class TestComputeHierarchy:
    def test_single_node(self):
        b = TopologyBuilder()
        b.add_node("A", "A", node_type="router")
        b.compute_hierarchy()
        assert b.nodes["A"]["level"] == 0
        assert b.nodes["A"]["parent_id"] is None
        assert b.nodes["A"]["role"] == "gateway"

    def test_linear_chain(self):
        b = TopologyBuilder()
        b.add_node("GW", "Gateway", node_type="router")
        b.add_node("SW", "Switch", node_type="switch")
        b.add_node("EP", "Endpoint", node_type="host")
        b.add_link("GW", "SW")
        b.add_link("SW", "EP")
        b.compute_hierarchy(gateway_ip="GW")
        assert b.nodes["GW"]["level"] == 0
        assert b.nodes["SW"]["level"] == 1
        assert b.nodes["EP"]["level"] == 2
        assert b.nodes["GW"]["parent_id"] is None
        assert b.nodes["SW"]["parent_id"] == "GW"
        assert b.nodes["EP"]["parent_id"] == "SW"

    def test_auto_root_selection(self):
        b = TopologyBuilder()
        b.add_node("A", "A", node_type="host")
        b.add_node("B", "B", node_type="switch")
        b.add_node("C", "C", node_type="host")
        b.add_node("D", "D", node_type="host")
        b.add_link("B", "A")
        b.add_link("B", "C")
        b.add_link("B", "D")
        b.compute_hierarchy(neighbor_counts={"B": 3, "A": 1, "C": 1, "D": 1})
        assert b.nodes["B"]["level"] == 0
        assert b.nodes["B"]["role"] == "gateway"

    def test_disconnected_non_ip_nodes_attached_to_root(self):
        b = TopologyBuilder()
        b.add_node("A", "A", node_type="router")
        b.add_node("B", "B", node_type="host")
        b.compute_hierarchy(gateway_ip="A")
        assert b.nodes["A"]["level"] == 0
        # Non-IP nodes get attached to root via subnet fallback
        assert b.nodes["B"]["parent_id"] == "A"
        assert b.nodes["B"]["level"] == 1

    def test_star_topology(self):
        b = TopologyBuilder()
        b.add_node("CORE", "Core", node_type="switch")
        for i in range(5):
            b.add_node(f"EP{i}", f"EP{i}", node_type="host")
            b.add_link("CORE", f"EP{i}")
        b.compute_hierarchy(gateway_ip="CORE")
        assert b.nodes["CORE"]["level"] == 0
        for i in range(5):
            assert b.nodes[f"EP{i}"]["level"] == 1
            assert b.nodes[f"EP{i}"]["parent_id"] == "CORE"

    def test_role_assignment(self):
        b = TopologyBuilder()
        b.add_node("GW", "GW", node_type="router")
        b.add_node("SW", "SW", node_type="switch")
        b.add_node("EP", "EP", node_type="host")
        b.add_link("GW", "SW")
        b.add_link("SW", "EP")
        b.compute_hierarchy(
            gateway_ip="GW",
            neighbor_counts={"GW": 1, "SW": 2, "EP": 1},
        )
        assert b.nodes["GW"]["role"] == "gateway"
        assert b.nodes["SW"]["role"] == "distribution"
        assert b.nodes["EP"]["role"] == "access"

    def test_empty_topology(self):
        b = TopologyBuilder()
        b.compute_hierarchy()

    def test_to_json_includes_hierarchy(self):
        b = TopologyBuilder()
        b.add_node("A", "A", node_type="router")
        b.add_node("B", "B", node_type="host")
        b.add_link("A", "B")
        b.compute_hierarchy(gateway_ip="A")
        data = b.to_json()
        a_node = next(n for n in data["nodes"] if n["id"] == "A")
        b_node = next(n for n in data["nodes"] if n["id"] == "B")
        assert a_node["level"] == 0
        assert b_node["level"] == 1
        assert b_node["parent_id"] == "A"
        assert "role" in a_node
        assert "role" in b_node


class TestSubnetFallback:
    """Tests for subnet-based hierarchy when LLDP data is absent."""

    def test_single_subnet_gateway_is_root(self):
        """All devices in 192.168.88.0/24, .1 is gateway."""
        b = TopologyBuilder()
        b.add_node("192.168.88.1", "Switch", node_type="switch")
        b.add_node("192.168.88.10", "PC-1", node_type="host")
        b.add_node("192.168.88.20", "PC-2", node_type="host")
        b.add_node("192.168.88.251", "NAS", node_type="server")
        b.compute_hierarchy(gateway_ip="192.168.88.1")
        assert b.nodes["192.168.88.1"]["level"] == 0
        assert b.nodes["192.168.88.1"]["parent_id"] is None
        # All others are children of .1
        for ip in ["192.168.88.10", "192.168.88.20", "192.168.88.251"]:
            assert b.nodes[ip]["parent_id"] == "192.168.88.1"
            assert b.nodes[ip]["level"] == 1
        # Synthetic links created
        assert len(b.links) >= 3

    def test_multi_subnet_router_bridges(self):
        """Two subnets: 192.168.88.0/24 and 192.168.2.0/24."""
        b = TopologyBuilder()
        b.add_node("192.168.88.1", "Main-Switch", node_type="switch")
        b.add_node("192.168.88.100", "Desktop", node_type="host")
        b.add_node("192.168.2.1", "Mesh-Router", node_type="router")
        b.add_node("192.168.2.50", "WiFi-Client", node_type="host")
        b.compute_hierarchy(gateway_ip="192.168.88.1")
        # Root subnet: 192.168.88.1 is root
        assert b.nodes["192.168.88.1"]["level"] == 0
        assert b.nodes["192.168.88.100"]["parent_id"] == "192.168.88.1"
        # Second subnet: 192.168.2.1 is subnet gateway, parent is root
        assert b.nodes["192.168.2.1"]["parent_id"] == "192.168.88.1"
        assert b.nodes["192.168.2.50"]["parent_id"] == "192.168.2.1"
        # Levels: root=0, subnet_gw=1, children=2
        assert b.nodes["192.168.2.1"]["level"] == 1
        assert b.nodes["192.168.2.50"]["level"] == 2

    def test_no_lldp_all_disconnected_gets_structure(self):
        """No LLDP links at all — subnet fallback provides full hierarchy."""
        b = TopologyBuilder()
        b.add_node("10.0.0.1", "GW", node_type="router")
        b.add_node("10.0.0.10", "Server", node_type="server")
        b.add_node("10.0.0.20", "PC", node_type="host")
        b.compute_hierarchy(gateway_ip="10.0.0.1")
        # All nodes should have parent_id set (except root)
        assert b.nodes["10.0.0.1"]["parent_id"] is None
        assert b.nodes["10.0.0.10"]["parent_id"] == "10.0.0.1"
        assert b.nodes["10.0.0.20"]["parent_id"] == "10.0.0.1"
        # Synthetic links created for DAG
        assert len(b.links) >= 2

    def test_subnet_gateway_picked_by_ip_priority(self):
        """When no explicit gateway, .1 address is picked as subnet gateway."""
        b = TopologyBuilder()
        b.add_node("172.16.0.1", "Router", node_type="router")
        b.add_node("172.16.0.50", "PC", node_type="host")
        b.add_node("172.16.0.100", "Printer", node_type="host")
        # No explicit gateway_ip — auto-select
        b.compute_hierarchy()
        # .1 should be root (lowest IP sort key)
        assert b.nodes["172.16.0.1"]["level"] == 0
        assert b.nodes["172.16.0.1"]["parent_id"] is None
        assert b.nodes["172.16.0.50"]["parent_id"] == "172.16.0.1"
        assert b.nodes["172.16.0.100"]["parent_id"] == "172.16.0.1"

    def test_infra_rank_breaks_ip_tie(self):
        """When two IPs have same sort priority, infra rank wins."""
        b = TopologyBuilder()
        b.add_node("10.0.0.5", "Switch", node_type="switch")
        b.add_node("10.0.0.6", "PC", node_type="host")
        b.add_node("10.0.0.7", "Laptop", node_type="host")
        b.compute_hierarchy()
        # Switch (rank 3) should be picked over hosts (rank 0) even with higher IP
        assert b.nodes["10.0.0.5"]["level"] == 0
        assert b.nodes["10.0.0.5"]["role"] == "gateway"

    def test_synthetic_links_created_for_dag(self):
        """Subnet fallback must create links so d3-dag has edges."""
        b = TopologyBuilder()
        b.add_node("192.168.1.1", "GW", node_type="router")
        b.add_node("192.168.1.10", "A", node_type="host")
        b.add_node("192.168.1.20", "B", node_type="host")
        b.compute_hierarchy(gateway_ip="192.168.1.1")
        # Should have synthetic links
        link_pairs = {(l["source"], l["target"]) for l in b.links}
        assert ("192.168.1.1", "192.168.1.10") in link_pairs or ("192.168.1.10", "192.168.1.1") in link_pairs
        assert ("192.168.1.1", "192.168.1.20") in link_pairs or ("192.168.1.20", "192.168.1.1") in link_pairs

    def test_mixed_lldp_and_subnet_fallback(self):
        """Some devices have LLDP links, others need subnet fallback."""
        b = TopologyBuilder()
        b.add_node("192.168.1.1", "Router", node_type="router")
        b.add_node("192.168.1.2", "Switch", node_type="switch")
        b.add_node("192.168.1.100", "PC-NoLLDP", node_type="host")
        b.add_node("192.168.1.200", "NAS-NoLLDP", node_type="server")
        # Only router-switch has LLDP
        b.add_link("192.168.1.1", "192.168.1.2")
        b.compute_hierarchy(gateway_ip="192.168.1.1")
        # BFS covers router and switch
        assert b.nodes["192.168.1.1"]["level"] == 0
        assert b.nodes["192.168.1.2"]["level"] == 1
        # Subnet fallback covers the rest — they become children of root
        # (since root is in same subnet and already visited)
        assert b.nodes["192.168.1.100"]["parent_id"] is not None
        assert b.nodes["192.168.1.200"]["parent_id"] is not None
        # No node should have level=99
        for nid in b.nodes:
            assert b.nodes[nid]["level"] != 99

    def test_real_world_homelab_scenario(self):
        """User's actual network: switch at .1, mesh router at different subnet, devices."""
        b = TopologyBuilder()
        b.add_node("192.168.88.1", "MikroTik-Switch", node_type="switch")
        b.add_node("192.168.88.251", "NAS", node_type="server")
        b.add_node("192.168.88.100", "Desktop", node_type="host")
        b.add_node("192.168.2.1", "Mesh-Router", node_type="router")
        b.add_node("192.168.2.10", "WiFi-Laptop", node_type="host")
        b.compute_hierarchy(gateway_ip="192.168.88.1")
        # Root: 192.168.88.1
        assert b.nodes["192.168.88.1"]["level"] == 0
        assert b.nodes["192.168.88.1"]["role"] == "gateway"
        # Same-subnet devices are children of switch
        assert b.nodes["192.168.88.251"]["parent_id"] == "192.168.88.1"
        assert b.nodes["192.168.88.100"]["parent_id"] == "192.168.88.1"
        # Cross-subnet: mesh router is child of root switch
        assert b.nodes["192.168.2.1"]["parent_id"] == "192.168.88.1"
        # Mesh router's client is child of mesh router
        assert b.nodes["192.168.2.10"]["parent_id"] == "192.168.2.1"
        # DAG has edges for all parent-child relationships
        assert len(b.links) >= 4
