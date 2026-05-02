"""Service Check Scheduler - Orchestrates periodic service checks."""

import asyncio
import time
from typing import Any, Callable, Optional

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus
from .http_check import HTTPCheckExecutor
from .tcp_check import TCPCheckExecutor
from .dns_check import DNSCheckExecutor
from .ping_check import PingCheckExecutor
from .ssl_check import SSLCheckExecutor


class CheckScheduler:
    """Orchestrates periodic service checks."""

    def __init__(self, db_client: Any):
        self.db_client = db_client
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._executors: dict[str, CheckExecutor] = {
            "http": HTTPCheckExecutor(),
            "tcp": TCPCheckExecutor(),
            "dns": DNSCheckExecutor(),
            "ping": PingCheckExecutor(),
            "ssl": SSLCheckExecutor(),
        }
        self._check_definitions: dict[str, CheckDefinition] = {}
        self._on_check_result: Optional[Callable] = None
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
        await self._schedule_all_checks()

    async def stop(self):
        """Stop the check scheduler."""
        self._running = False

        # Cancel all scheduled tasks
        for task in self._tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()

    async def _load_checks_from_db(self):
        """Load check definitions from database."""
        # This will be implemented when we add the check tables to DB
        # For now, load from in-memory config
        pass

    async def _schedule_all_checks(self):
        """Schedule all check definitions."""
        for check_id, definition in self._check_definitions.items():
            if definition.enabled and check_id not in self._tasks:
                self._tasks[check_id] = asyncio.create_task(
                    self._run_periodic_check(definition)
                )

    async def _run_periodic_check(self, definition: CheckDefinition):
        """Run a check periodically."""
        while self._running and definition.enabled:
            try:
                await self._execute_check(definition)
            except Exception as e:
                print(f"[CheckScheduler] Error executing check {definition.id}: {e}")

            await asyncio.sleep(definition.interval_seconds)

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

        # Start scheduling if running and enabled
        if self._running and definition.enabled and definition.id not in self._tasks:
            self._tasks[definition.id] = asyncio.create_task(
                self._run_periodic_check(definition)
            )

    def remove_check(self, check_id: str):
        """Remove a check definition."""
        if check_id in self._tasks:
            self._tasks[check_id].cancel()
            del self._tasks[check_id]

        if check_id in self._check_definitions:
            del self._check_definitions[check_id]

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        return {
            **self._stats,
            "running": self._running,
            "scheduled_checks": len(self._check_definitions),
            "active_tasks": len(self._tasks),
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
