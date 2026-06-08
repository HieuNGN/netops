"""Runtime network-change watcher.

Periodic background task that re-runs `host_state.detect_and_compare`.
If the detected (cidr, gateway) fingerprint changes from the stored one,
broadcasts a `network_changed` SSE event and enqueues a merge-based
rescan of the new CIDR.

Interval configurable via `NETOPS_NETWORK_CHECK_INTERVAL` (default
60s). Disable with `NETOPS_NETWORK_CHECK_INTERVAL=0`.
"""

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from .host_state import detect_and_compare, set_host_state

logger = logging.getLogger("netops.network_watcher")


class NetworkWatcher:
    """Periodic (cidr, gateway) fingerprint watcher."""

    def __init__(
        self,
        db_client: Any,
        on_network_change: Callable[[dict[str, Any]], Awaitable[None]],
        interval_seconds: Optional[int] = None,
    ):
        self.db_client = db_client
        self._on_network_change = on_network_change
        self.interval_seconds = (
            int(os.getenv("NETOPS_NETWORK_CHECK_INTERVAL", "60"))
            if interval_seconds is None
            else interval_seconds
        )
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_fingerprint: Optional[str] = None
        self._last_cidr: Optional[str] = None
        self._check_count: int = 0

    async def start(self) -> None:
        if self.interval_seconds <= 0:
            logger.info("NetworkWatcher disabled (interval=0)")
            return
        if self._running:
            return

        try:
            if hasattr(self.db_client, "get_setting"):
                stored = await self.db_client.get_setting("host_fingerprint")
                if isinstance(stored, str) and stored:
                    self._last_fingerprint = stored
                    stored_cidr = await self.db_client.get_setting("host_cidr")
                    if isinstance(stored_cidr, str):
                        self._last_cidr = stored_cidr
                    logger.info(
                        f"NetworkWatcher seeded from DB: "
                        f"cidr={self._last_cidr} fp={self._last_fingerprint[:8]}..."
                    )
        except Exception:
            pass

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"NetworkWatcher started (interval={self.interval_seconds}s, "
            f"last_fp={self._last_fingerprint[:8] if self._last_fingerprint else 'none'})"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def check_once(self) -> Optional[dict[str, Any]]:
        """Run a single check. Returns the snapshot dict on change, else None."""
        self._check_count += 1
        try:
            snap = await detect_and_compare(self.db_client)
        except Exception as e:
            logger.warning(f"NetworkWatcher check failed: {e}")
            return None
        fp = snap.get("fingerprint")
        detected = snap.get("detected", {}) or {}
        cidr = detected.get("cidr") or "?"

        if not fp:
            logger.debug(
                f"NetworkWatcher tick#{self._check_count}: "
                f"no fingerprint (cidr={cidr}) — skipping"
            )
            return None

        if self._last_fingerprint is None:
            self._last_fingerprint = fp
            self._last_cidr = cidr
            logger.info(
                f"NetworkWatcher tick#{self._check_count}: "
                f"first check, seed fp={fp[:8]}... cidr={cidr}"
            )
            return None

        if fp == self._last_fingerprint:
            logger.debug(
                f"NetworkWatcher tick#{self._check_count}: "
                f"no change (fp={fp[:8]}... cidr={cidr})"
            )
            return None

        prev_fp = self._last_fingerprint
        prev_cidr = self._last_cidr
        self._last_fingerprint = fp
        self._last_cidr = cidr

        logger.info(
            f"NetworkWatcher tick#{self._check_count}: NETWORK CHANGED "
            f"cidr={prev_cidr}→{cidr} fp={prev_fp[:8]}→{fp[:8]}"
        )

        await set_host_state(
            self.db_client,
            snap["detected"].get("cidr") or "",
            snap["detected"].get("gateway"),
        )
        try:
            await self._on_network_change(snap)
        except Exception as e:
            logger.warning(f"NetworkWatcher on_change handler error: {e}")
        return snap

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"NetworkWatcher loop error: {e}")
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "last_fingerprint": self._last_fingerprint,
            "last_cidr": self._last_cidr,
            "check_count": self._check_count,
        }
