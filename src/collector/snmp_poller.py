"""SNMP Poller Service - Periodic polling orchestrator for network devices."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .spike_snmp import get_sys_descr_async, walk_lldp_neighbors_async, _build_auth
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
        self._retention_task: Optional[asyncio.Task] = None
        self._topology_builder = TopologyBuilder()
        self._on_topology_change: Optional[Callable] = None
        self._poll_semaphore = asyncio.Semaphore(5)  # Cap concurrent SNMP polls

    def set_topology_change_handler(self, handler: Callable):
        """Set callback for topology changes."""
        self._on_topology_change = handler

    async def start(self):
        """Start the polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        self._retention_task = asyncio.create_task(self._retention_loop())

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        for t in [self._task, getattr(self, '_retention_task', None)]:
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._retention_task = None

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

    async def _retention_loop(self):
        """Periodic cleanup of old poll history."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # hourly
                await self.db_client.cleanup_poll_history(retention_days=30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SNMPPoller] Retention cleanup error: {e}")

    async def _poll_all_devices(self):
        """Poll all configured devices."""
        devices = await self.db_client.list_devices()

        if not devices:
            return

        results = []
        self._topology_builder.clear()

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
        changes = await self.db_client.upsert_topology(
            current_topology["nodes"], current_topology["links"]
        )

        # Trigger change handler only when changes exist or status flipped
        has_changes = any(v > 0 for v in changes.values())
        if self._on_topology_change and has_changes:
            await self._on_topology_change(changes, current_topology)

    async def _poll_device(self, device: dict[str, Any]) -> PollResult:
        """Poll a single device with v2c or v3 support."""
        import time

        self.stats.total_polls += 1
        start_time = time.time()

        try:
            ip = device["ip_address"]

            async with self._poll_semaphore:
                auth = _build_auth(device)
                sys_descr = await get_sys_descr_async(ip, auth)
                neighbors = await walk_lldp_neighbors_async(ip, auth)

            response_time = (time.time() - start_time) * 1000
            self.stats.add_response_time(response_time)
            self.stats.successful_polls += 1

            # Update device in database
            await self.db_client.update_device(
                device["id"],
                {
                    "status": "online",
                    "sys_descr": sys_descr or "",
                    "last_polled": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

            # Record poll result
            await self.db_client.add_poll_result(
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
            await self.db_client.update_device(
                device["id"], {"status": "offline", "last_polled": time.strftime("%Y-%m-%d %H:%M:%S")}
            )

            # Record poll failure
            await self.db_client.add_poll_result(device["id"], "offline", 0, error_msg)

            return PollResult(
                device_id=device["id"],
                ip_address=device["ip_address"],
                success=False,
                error=error_msg,
            )

    def _build_topology_links(
        self, devices: list[dict[str, Any]], results: list[PollResult]
    ):
        """Build topology links from LLDP neighbor data with multi-strategy matching."""
        ip_to_device = {d["ip_address"]: d for d in devices}
        name_to_device: dict[str, Any] = {}
        for d in devices:
            if d.get("name"):
                name_to_device[d["name"].lower()] = d

        for device, result in zip(devices, results):
            if not result.success:
                continue

            for neighbor in result.neighbors:
                neighbor_name = neighbor.get("neighbor_name", "")
                neighbor_port = neighbor.get("neighbor_port", "")

                target_device = None

                if neighbor_name == device["ip_address"]:
                    continue
                if neighbor_name.lower() == device.get("name", "").lower():
                    continue

                if neighbor_name in ip_to_device:
                    target_device = ip_to_device[neighbor_name]
                elif neighbor_name.lower() in name_to_device:
                    target_device = name_to_device[neighbor_name.lower()]
                else:
                    for d in devices:
                        if d["ip_address"] == device["ip_address"]:
                            continue
                        d_name = d.get("name", "").lower()
                        n_name = neighbor_name.lower()
                        if d_name and n_name and (
                            n_name == d_name or
                            d_name in n_name or
                            n_name in d_name
                        ):
                            target_device = d
                            break

                if target_device:
                    self._topology_builder.add_link(
                        source=device["ip_address"],
                        target=target_device["ip_address"],
                        source_port=neighbor_port,
                        target_port="",
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
        devices = await self.db_client.list_devices()
        results = []
        for device in devices:
            result = await self._poll_device(device)
            results.append(result)
        return results
