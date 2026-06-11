"""SNMP Poller Service - Periodic polling orchestrator for network devices."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .spike_snmp import (
    get_sys_descr_async,
    get_sys_name_async,
    walk_lldp_neighbors_async,
    _build_auth,
)
from .topology_builder import TopologyBuilder, classify_device


@dataclass
class PollResult:
    """Result of a single device poll."""

    device_id: str
    ip_address: str
    success: bool
    sys_descr: Optional[str] = None
    sys_name: Optional[str] = None
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
        self._on_status_change: Optional[Callable] = None
        self._last_status: dict[str, str] = {}
        self._poll_semaphore = asyncio.Semaphore(5)

    def set_topology_change_handler(self, handler: Callable):
        self._on_topology_change = handler

    def set_status_change_handler(self, handler: Callable):
        self._on_status_change = handler

    def set_anomaly_detector(self, detector: Any):
        """Set the anomaly detector instance for recording metrics."""
        self._anomaly_detector = detector

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        self._retention_task = asyncio.create_task(self._retention_loop())

    async def stop(self):
        self._running = False
        for t in [self._task, getattr(self, "_retention_task", None)]:
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._retention_task = None

    async def _poll_loop(self):
        while self._running:
            try:
                await self._poll_all_devices()
                self.stats.last_poll_time = time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"[SNMPPoller] Error in poll loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _retention_loop(self):
        while self._running:
            try:
                await asyncio.sleep(3600)

                poll_retention = 30
                topo_retention = 90
                if hasattr(self.db_client, "get_setting"):
                    try:
                        v = await self.db_client.get_setting(
                            "poll_history_retention_days"
                        )
                        if isinstance(v, int) and v > 0:
                            poll_retention = v
                    except Exception:
                        pass
                    try:
                        v = await self.db_client.get_setting(
                            "topology_history_retention_days"
                        )
                        if isinstance(v, int) and v > 0:
                            topo_retention = v
                    except Exception:
                        pass

                await self.db_client.cleanup_poll_history(
                    retention_days=poll_retention,
                )
                if hasattr(self.db_client, "cleanup_topology_history"):
                    try:
                        await self.db_client.cleanup_topology_history(
                            retention_days=topo_retention,
                        )
                    except Exception as inner_e:
                        print(
                            f"[SNMPPoller] Topology history cleanup error: {inner_e}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SNMPPoller] Retention cleanup error: {e}")

    async def _poll_all_devices(self):
        devices = await self.db_client.list_devices()

        if not devices:
            return

        results = []
        self._topology_builder.clear()
        neighbor_counts: dict[str, int] = {}

        for device in devices:
            try:
                result = await self._poll_device(device)
            except Exception as e:
                print(f"[SNMPPoller] _poll_device raised for {device.get('id')}: {e}")
                result = PollResult(
                    device_id=device.get("id", ""),
                    ip_address=device.get("ip_address", ""),
                    success=False,
                    error=str(e),
                )
            results.append(result)

            status = "online" if result.success else "offline"
            node_type = classify_device(
                sys_descr=result.sys_descr,
                name=device.get("name"),
            )
            neighbor_counts[device["ip_address"]] = len(result.neighbors)
            self._topology_builder.add_node(
                node_id=device["ip_address"],
                label=device.get("name", device["ip_address"]),
                device_id=device["id"],
                node_type=node_type,
                status=status,
                sys_descr=result.sys_descr,
            )

        # --- Fetch gateway before building links ---
        gateway_ip = None
        if hasattr(self.db_client, "get_setting"):
            try:
                gateway_ip = await self.db_client.get_setting("host_gateway")
            except Exception:
                pass

        # Only build LLDP links from gateway if known; otherwise all devices
        self._build_topology_links(devices, results, gateway_ip=gateway_ip)

        self._topology_builder.compute_hierarchy(
            gateway_ip=gateway_ip,
            neighbor_counts=neighbor_counts,
        )

        current_topology = self._topology_builder.to_json()
        try:
            changes = await self.db_client.upsert_topology(
                current_topology["nodes"], current_topology["links"]
            )
        except Exception as e:
            print(f"[SNMPPoller] upsert_topology failed: {e}")
            changes = {"nodes_added": 0, "nodes_removed": 0, "links_added": 0, "links_removed": 0}

        status_flips = sum(
            1 for r in results
            if self._last_status.get(r.device_id) is not None
            and self._last_status.get(r.device_id) != ("online" if r.success else "offline")
        )
        if status_flips:
            changes["status_changed"] = status_flips

        has_changes = any(v > 0 for v in changes.values())
        if self._on_topology_change and has_changes:
            await self._on_topology_change(changes, current_topology)

    async def _poll_device(self, device: dict[str, Any]) -> PollResult:
        import time
        from datetime import datetime, timezone

        self.stats.total_polls += 1
        start_time = time.time()

        try:
            ip = device["ip_address"]

            async with self._poll_semaphore:
                auth = _build_auth(device)
                # sysDescr is required — if this fails, device is offline
                sys_descr = await get_sys_descr_async(ip, auth)

                # sysName is optional — used to auto-update device name
                sys_name = None
                try:
                    sys_name = await get_sys_name_async(ip, auth)
                except Exception as name_err:
                    import logging
                    logging.getLogger(__name__).debug(
                        f"sysName fetch failed for {ip}: {name_err}"
                    )

                # LLDP walk is optional — many devices don't support it
                # If it fails, device is still online, just no topology links
                try:
                    neighbors = await walk_lldp_neighbors_async(ip, auth)
                except Exception as lldp_err:
                    import logging
                    logging.getLogger(__name__).debug(
                        f"LLDP walk failed for {ip} (device still online): {lldp_err}"
                    )
                    neighbors = []

            response_time = (time.time() - start_time) * 1000
            self.stats.add_response_time(response_time)
            self.stats.successful_polls += 1

            # Auto-update device name from SNMP sysName if returned and differs
            update_payload = {
                "status": "online",
                "sys_descr": sys_descr or "",
                "last_polled": time.strftime("%Y-%m-%d %H:%M:%S"),
                "offline_since": None,
            }
            current_name = device.get("name", "").strip()
            if sys_name and sys_name != current_name:
                update_payload["name"] = sys_name

            try:
                await self.db_client.update_device(
                    device["id"],
                    update_payload,
                )
            except Exception as e:
                print(f"[SNMPPoller] update_device failed for {device['id']}: {e}")

            try:
                await self.db_client.add_poll_result(
                    device["id"], "online", response_time, ""
                )
            except Exception as e:
                print(f"[SNMPPoller] add_poll_result failed for {device['id']}: {e}")

            # Feed response time to anomaly detector
            if hasattr(self, '_anomaly_detector') and self._anomaly_detector:
                try:
                    anomaly = await self._anomaly_detector.record_value(
                        "response_time", device["id"], response_time
                    )
                    if anomaly:
                        import logging
                        logging.getLogger(__name__).warning(
                            f"Anomaly detected for {device['id']}: "
                            f"response_time={anomaly['current_value']}ms "
                            f"(baseline={anomaly['baseline_avg']}±{anomaly['baseline_std']}ms, "
                            f"z={anomaly['z_score']})"
                        )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"anomaly_detector.record_value failed: {e}")

            await self._emit_status_change(
                device, "online", None, response_time_ms=response_time,
            )

            return PollResult(
                device_id=device["id"],
                ip_address=ip,
                success=True,
                sys_descr=sys_descr,
                sys_name=sys_name,
                neighbors=neighbors,
                response_time_ms=response_time,
            )

        except Exception as e:
            self.stats.failed_polls += 1
            error_msg = str(e)

            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                await self.db_client.update_device(
                    device["id"],
                    {
                        "status": "offline",
                        "offline_since": now_iso,
                        "last_polled": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
            except Exception as inner_e:
                try:
                    await self.db_client.update_device(
                        device["id"],
                        {"status": "offline", "last_polled": time.strftime("%Y-%m-%d %H:%M:%S")},
                    )
                except Exception:
                    print(f"[SNMPPoller] update_device failed for {device['id']}: {inner_e}")

            try:
                await self.db_client.add_poll_result(device["id"], "offline", 0, error_msg)
            except Exception as poll_e:
                print(f"[SNMPPoller] add_poll_result failed for {device['id']}: {poll_e}")

            await self._emit_status_change(
                device, "offline", error_msg, response_time_ms=0,
            )

            return PollResult(
                device_id=device["id"],
                ip_address=device["ip_address"],
                success=False,
                error=error_msg,
            )

    async def _emit_status_change(
        self,
        device: dict[str, Any],
        new_status: str,
        error: Optional[str],
        response_time_ms: float = 0,
    ) -> None:
        prev = self._last_status.get(device["id"])
        if prev == new_status:
            return
        self._last_status[device["id"]] = new_status
        if self._on_status_change is None:
            return
        try:
            await self._on_status_change(
                {
                    "device_id": device["id"],
                    "ip_address": device.get("ip_address"),
                    "name": device.get("name", ""),
                    "old_status": prev,
                    "new_status": new_status,
                    "error": error,
                    "response_time_ms": response_time_ms,
                }
            )
        except Exception as e:
            print(f"[SNMPPoller] status change handler error: {e}")

    def _build_topology_links(
        self, devices: list[dict[str, Any]], results: list[PollResult], gateway_ip: Optional[str] = None
    ):
        ip_to_device = {d["ip_address"]: d for d in devices}
        name_to_device: dict[str, Any] = {}
        for d in devices:
            if d.get("name"):
                name_to_device[d["name"].lower()] = d

        def _resolve_neighbor(device, neighbor_name, neighbor_port):
            if neighbor_name == device["ip_address"]:
                return None
            if neighbor_name.lower() == device.get("name", "").lower():
                return None

            if neighbor_name in ip_to_device:
                return ip_to_device[neighbor_name]
            if neighbor_name.lower() in name_to_device:
                return name_to_device[neighbor_name.lower()]
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
                    return d
            return None

        # If gateway is known, only use its LLDP to avoid duplicate/conflicting sources
        if gateway_ip:
            gateway_device = ip_to_device.get(gateway_ip)
            if gateway_device:
                for device, result in zip(devices, results):
                    if not result.success or device["ip_address"] != gateway_ip:
                        continue
                    for neighbor in result.neighbors:
                        target = _resolve_neighbor(device, neighbor.get("neighbor_name", ""), neighbor.get("neighbor_port", ""))
                        if target:
                            self._topology_builder.add_link(
                                source=device["ip_address"],
                                target=target["ip_address"],
                                source_port=neighbor.get("neighbor_port", ""),
                                target_port="",
                            )
                return

        # Fallback: process all devices
        for device, result in zip(devices, results):
            if not result.success:
                continue
            for neighbor in result.neighbors:
                target = _resolve_neighbor(device, neighbor.get("neighbor_name", ""), neighbor.get("neighbor_port", ""))
                if target:
                    self._topology_builder.add_link(
                        source=device["ip_address"],
                        target=target["ip_address"],
                        source_port=neighbor.get("neighbor_port", ""),
                        target_port="",
                    )

    def get_stats(self) -> dict[str, Any]:
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
        """Trigger an immediate poll of all devices. Returns results."""
        devices = await self.db_client.list_devices()
        if not devices:
            return []
        results = []
        self._topology_builder.clear()
        neighbor_counts: dict[str, int] = {}
        for device in devices:
            try:
                result = await self._poll_device(device)
            except Exception as e:
                print(f"[SNMPPoller] _poll_device raised for {device.get('id')}: {e}")
                result = PollResult(
                    device_id=device.get("id", ""),
                    ip_address=device.get("ip_address", ""),
                    success=False,
                    error=str(e),
                )
            results.append(result)
            status = "online" if result.success else "offline"
            node_type = classify_device(
                sys_descr=result.sys_descr,
                name=device.get("name"),
            )
            neighbor_counts[device["ip_address"]] = len(result.neighbors)
            self._topology_builder.add_node(
                node_id=device["ip_address"],
                label=device.get("name", device["ip_address"]),
                device_id=device["id"],
                node_type=node_type,
                status=status,
                sys_descr=result.sys_descr,
            )
        gateway_ip = None
        if hasattr(self.db_client, "get_setting"):
            try:
                gateway_ip = await self.db_client.get_setting("host_gateway")
            except Exception:
                pass

        self._build_topology_links(devices, results, gateway_ip=gateway_ip)

        self._topology_builder.compute_hierarchy(
            gateway_ip=gateway_ip,
            neighbor_counts=neighbor_counts,
        )

        current_topology = self._topology_builder.to_json()
        try:
            await self.db_client.upsert_topology(
                current_topology["nodes"], current_topology["links"]
            )
        except Exception as e:
            print(f"[SNMPPoller] upsert_topology failed: {e}")
        return results
