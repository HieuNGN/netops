"""Service Check Scheduler - Orchestrates periodic service checks."""

import asyncio
import time
from typing import Any, Callable, Optional

from ..utils import logger
from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus
from .http_check import HTTPCheckExecutor
from .tcp_check import TCPCheckExecutor
from .dns_check import DNSCheckExecutor
from .ping_check import PingCheckExecutor
from .ssl_check import SSLCheckExecutor


class CheckScheduler:
    """Orchestrates periodic service checks with a single tick loop."""

    def __init__(self, db_client: Any):
        self.db_client = db_client
        self._running = False
        self._master_task: Optional[asyncio.Task] = None
        self._executors: dict[str, CheckExecutor] = {
            "http": HTTPCheckExecutor(),
            "tcp": TCPCheckExecutor(),
            "dns": DNSCheckExecutor(),
            "ping": PingCheckExecutor(),
            "ssl": SSLCheckExecutor(),
        }
        self._check_definitions: dict[str, CheckDefinition] = {}
        self._next_run: dict[str, float] = {}
        self._on_check_result: Optional[Callable] = None
        self._check_semaphore = asyncio.Semaphore(10)
        self._stats = {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "last_run": None,
        }

    def set_check_result_handler(self, handler: Callable):
        """Set callback for check results."""
        self._on_check_result = handler

    async def start(self):
        """Start the check scheduler."""
        if self._running:
            return

        self._running = True
        await self._load_checks_from_db()
        self._reset_next_run()
        self._master_task = asyncio.create_task(self._tick_loop())
        logger.info("Check scheduler started (single tick loop)")

    async def stop(self):
        """Stop the check scheduler."""
        self._running = False
        if self._master_task:
            self._master_task.cancel()
            try:
                await self._master_task
            except asyncio.CancelledError:
                pass
            self._master_task = None

    def _reset_next_run(self):
        """Initialize next run times for all enabled checks."""
        now = time.time()
        self._next_run = {
            cid: now + (i % max(1, len(self._check_definitions))) * 0.5
            for i, (cid, d) in enumerate(self._check_definitions.items())
            if d.enabled
        }

    async def _tick_loop(self):
        """Master tick loop: wakes every 1s and runs due checks."""
        while self._running:
            try:
                await self._run_due_checks()
            except Exception as e:
                print(f"[CheckScheduler] Error in tick loop: {e}")
            await asyncio.sleep(1.0)

    async def _run_due_checks(self):
        """Execute all checks whose next_run time has passed."""
        now = time.time()
        due = [
            (cid, self._check_definitions[cid])
            for cid, nxt in self._next_run.items()
            if nxt <= now and cid in self._check_definitions
        ]

        if not due:
            return

        async def run_one(cid: str, definition: CheckDefinition):
            async with self._check_semaphore:
                try:
                    await self._execute_check(definition)
                except Exception as e:
                    print(f"[CheckScheduler] Error executing check {cid}: {e}")
            # Stagger next run: add jitter so checks don't bunch after startup
            jitter = (hash(cid) % 10) / 10.0
            self._next_run[cid] = now + definition.interval_seconds + jitter

        await asyncio.gather(
            *[run_one(cid, d) for cid, d in due],
            return_exceptions=True,
        )

    async def _load_checks_from_db(self):
        """Load check definitions from database."""
        try:
            checks = await self.db_client.list_service_checks()
            for check in checks:
                definition = CheckDefinition(
                    id=check["id"],
                    name=check["name"],
                    check_type=check["check_type"],
                    target=check["target"],
                    interval_seconds=check["interval_seconds"],
                    timeout_seconds=check["timeout_seconds"],
                    enabled=bool(check["enabled"]),
                    config=check.get("config_json", {}),
                )
                self._check_definitions[definition.id] = definition
            logger.info(f"Loaded {len(checks)} service checks from database")
        except Exception as e:
            logger.warning(f"Failed to load checks from database: {e}")

    async def _execute_check(self, definition: CheckDefinition) -> CheckResult:
        """Execute a single check."""
        executor = self._executors.get(definition.check_type)

        if not executor:
            result = CheckResult(
                target_id=definition.id,
                check_type=definition.check_type,
                status=CheckStatus.UNKNOWN,
                response_time_ms=0,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                message=f"Unknown check type: {definition.check_type}",
                error=f"No executor for {definition.check_type}",
            )
        else:
            # Validate config before executing
            valid, error = executor.validate_config(definition.config)
            if not valid:
                result = CheckResult(
                    target_id=definition.id,
                    check_type=definition.check_type,
                    status=CheckStatus.UNKNOWN,
                    response_time_ms=0,
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    message="Invalid configuration",
                    error=error,
                )
            else:
                result = await executor.execute(definition)

        # Update stats
        self._stats["total_checks"] += 1
        if result.status in (CheckStatus.UP, CheckStatus.DEGRADED):
            self._stats["successful_checks"] += 1
        else:
            self._stats["failed_checks"] += 1
        self._stats["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Notify handler if set
        if self._on_check_result:
            await self._on_check_result(result)

        # Store result in database
        await self._store_check_result(result)

        return result

    async def _store_check_result(self, result: CheckResult):
        """Store check result in database."""
        if hasattr(self.db_client, "add_check_result"):
            await self.db_client.add_check_result(
                check_id=result.target_id,
                status=result.status.value,
                response_time_ms=result.response_time_ms,
                message=result.message,
                details=result.details,
                error=result.error,
            )

    async def run_check_now(self, check_id: str) -> Optional[CheckResult]:
        """Run a specific check immediately."""
        definition = self._check_definitions.get(check_id)
        if not definition:
            return None

        return await self._execute_check(definition)

    def add_check(self, definition: CheckDefinition):
        """Add a new check definition."""
        self._check_definitions[definition.id] = definition
        if definition.enabled:
            self._next_run[definition.id] = time.time()

    def remove_check(self, check_id: str):
        """Remove a check definition."""
        self._next_run.pop(check_id, None)
        self._check_definitions.pop(check_id, None)

    def apply_check_intervals(self, intervals: dict[str, int]):
        """Phase 2: apply per-type default intervals live.

        Adjusts the `next_run` time for any existing check whose
        `check_type` matches a key in `intervals`. New checks added
        after this call should use `default_interval_for(check_type)`
        in the request model.
        """
        now = time.time()
        for cid, d in self._check_definitions.items():
            new_interval = intervals.get(d.check_type)
            if not new_interval or new_interval <= 0:
                continue
            if d.interval_seconds == new_interval:
                continue
            d.interval_seconds = new_interval
            # Reschedule the next run to honor the new cadence.
            self._next_run[cid] = now

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        return {
            **self._stats,
            "running": self._running,
            "scheduled_checks": len(self._check_definitions),
            "active_tasks": 1 if self._master_task else 0,
        }

    def get_check_definitions(self) -> list[dict[str, Any]]:
        """Get all check definitions."""
        return [
            {
                "id": d.id,
                "name": d.name,
                "check_type": d.check_type,
                "target": d.target,
                "interval_seconds": d.interval_seconds,
                "timeout_seconds": d.timeout_seconds,
                "enabled": d.enabled,
                "config": d.config,
            }
            for d in self._check_definitions.values()
        ]
