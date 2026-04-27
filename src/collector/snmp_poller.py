"""SNMP Poller Service - Periodic polling orchestrator for network devices."""

import asyncio
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .spike_snmp import get_sys_descr, walk_lldp_neighbors
from .topology_builder import TopologyBuilder


@dataclass
class PollResult:
    """Result of a single device poll."""

    device_id: str
    ip_address: str
    success: bool
    sys_descr: Optional[str] = None
    neighbors: list[dict[str, Any]] = field(default_factory=list)
    response_time_ms: float = 0
    error: Optional[str] = None


@dataclass
class PollStats:
    """Statistics for polling operations."""

    total_polls: int = 0
    successful_polls: int = 0
    failed_polls: int = 0
    last_poll_time: Optional[str] = None
    avg_response_time_ms: float = 0
    _response_times: list[float] = field(default_factory=list, repr=False)

    def add_response_time(self, ms: float):
        self._response_times.append(ms)
        # Keep only last 100 for rolling average
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]
        self.avg_response_time_ms = sum(self._response_times) / len(self._response_times)


class SNMPPoller:
    """SNMP polling orchestrator with configurable interval."""

    def __init__(
        self,
        db_client: Any,
        poll_interval: int = 30,
        timeout: int = 5,
        retries: int = 3,
    ):
        self.db_client = db_client
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.retries = retries
        self.stats = PollStats()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._topology_builder = TopologyBuilder()
        self._on_topology_change: Optional[Callable] = None

    def set_topology_change_handler(self, handler: Callable):
        """Set callback for topology changes."""
        self._on_topology_change = handler

    async def start(self):
        """Start the polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_all_devices()
                self.stats.last_poll_time = time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                # Log but don't crash the poller
                print(f"[SNMPPoller] Error in poll loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _poll_all_devices(self):
        """Poll all configured devices."""
        devices = self.db_client.list_devices()

        if not devices:
            return

        results = []
        self._topology_builder = TopologyBuilder()

        for device in devices:
            result = await self._poll_device(device)
            results.append(result)

            # Add node to topology
            status = "online" if result.success else "offline"
            self._topology_builder.add_node(
                node_id=device["ip_address"],
                label=device.get("name", device["ip_address"]),
                device_id=device["id"],
                node_type="device",
                status=status,
                sys_descr=result.sys_descr,
            )

        # Build links from LLDP neighbors
        self._build_topology_links(devices, results)

        # Get current topology and detect changes
        current_topology = self._topology_builder.to_json()
        changes = self.db_client.upsert_topology(
            current_topology["nodes"], current_topology["links"]
        )

        # Trigger change handler if there are changes
        if self._on_topology_change and any(
            v > 0 for v in changes.values() if isinstance(v, int)
        ):
            await self._on_topology_change(changes, current_topology)

    async def _poll_device(self, device: dict[str, Any]) -> PollResult:
        """Poll a single device."""
        import time

        self.stats.total_polls += 1
        start_time = time.time()

        try:
            ip = device["ip_address"]
            community = device.get("community", "public")

            # Run SNMP queries in executor to avoid blocking
            loop = asyncio.get_event_loop()

            # Get sysDescr
            sys_descr = await loop.run_in_executor(
                None, get_sys_descr, ip, community
            )

            # Get LLDP neighbors
            neighbors = await loop.run_in_executor(
                None, walk_lldp_neighbors, ip, community
            )

            response_time = (time.time() - start_time) * 1000
            self.stats.add_response_time(response_time)
            self.stats.successful_polls += 1

            # Update device in database
            self.db_client.update_device(
                device["id"],
                {
                    "status": "online",
                    "sys_descr": sys_descr or "",
                    "last_polled": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

            # Record poll result
            self.db_client.add_poll_result(
                device["id"], "online", response_time, ""
            )

            return PollResult(
                device_id=device["id"],
                ip_address=ip,
                success=True,
                sys_descr=sys_descr,
                neighbors=neighbors,
                response_time_ms=response_time,
            )

        except Exception as e:
            self.stats.failed_polls += 1
            error_msg = str(e)

            # Update device status
            self.db_client.update_device(
                device["id"], {"status": "offline", "last_polled": time.strftime("%Y-%m-%d %H:%M:%S")}
            )

            # Record poll failure
            self.db_client.add_poll_result(device["id"], "offline", 0, error_msg)

            return PollResult(
                device_id=device["id"],
                ip_address=device["ip_address"],
                success=False,
                error=error_msg,
            )

    def _build_topology_links(
        self, devices: list[dict[str, Any]], results: list[PollResult]
    ):
        """Build topology links from LLDP neighbor data."""
        # Create IP -> device mapping
        ip_to_device = {d["ip_address"]: d for d in devices}

        # Build links from LLDP data
        for device, result in zip(devices, results):
            if not result.success:
                continue

            for neighbor in result.neighbors:
                neighbor_name = neighbor.get("neighbor_name", "")
                neighbor_port = neighbor.get("neighbor_port", "")

                # Try to find the neighbor device in our device list
                # Match by name (sysName) or IP
                target_device = None
                for d in devices:
                    if d["ip_address"] == device["ip_address"]:
                        continue
                    # Match by name substring or exact IP
                    if neighbor_name.lower() in d.get("name", "").lower():
                        target_device = d
                        break
                    if neighbor_name == d["ip_address"]:
                        target_device = d
                        break

                if target_device:
                    self._topology_builder.add_link(
                        source=device["ip_address"],
                        target=target_device["ip_address"],
                        source_port=neighbor_port,
                        target_port="",  # Would need reverse LLDP query
                    )

    def get_stats(self) -> dict[str, Any]:
        """Get polling statistics."""
        return {
            "total_polls": self.stats.total_polls,
            "successful_polls": self.stats.successful_polls,
            "failed_polls": self.stats.failed_polls,
            "success_rate": (
                self.stats.successful_polls / self.stats.total_polls
                if self.stats.total_polls > 0
                else 0
            ),
            "last_poll_time": self.stats.last_poll_time,
            "avg_response_time_ms": self.stats.avg_response_time_ms,
            "poll_interval": self.poll_interval,
            "running": self._running,
        }

    async def poll_now(self) -> list[PollResult]:
        """Trigger an immediate poll of all devices."""
        await self._poll_all_devices()
        devices = self.db_client.list_devices()
        results = []
        for device in devices:
            result = await self._poll_device(device)
            results.append(result)
        return results
