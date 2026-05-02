"""TCP service check executor."""

import asyncio
import socket
import time
from typing import Any, Optional

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus


class TCPCheckExecutor(CheckExecutor):
    """Execute TCP port connectivity checks."""

    @property
    def check_type(self) -> str:
        return "tcp"

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate TCP check configuration."""
        if "host" not in config:
            return False, "Host is required for TCP checks"

        if "port" not in config:
            return False, "Port is required for TCP checks"

        port = config["port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            return False, "Port must be between 1 and 65535"

        return True, ""

    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute TCP check."""
        host = definition.config.get("host", definition.target.split(":")[0] if ":" in definition.target else definition.target)
        port = definition.config.get("port")

        # Parse port from target if not in config (e.g., "host:port")
        if port is None and ":" in definition.target:
            try:
                port = int(definition.target.split(":")[1])
            except ValueError:
                return CheckResult(
                    target_id=definition.id,
                    check_type=self.check_type,
                    status=CheckStatus.DOWN,
                    response_time_ms=0,
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    message="Invalid port in target",
                    error="Port must be a number",
                )

        if port is None:
            return CheckResult(
                target_id=definition.id,
                check_type=self.check_type,
                status=CheckStatus.UNKNOWN,
                response_time_ms=0,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                message="Port not specified",
                error="Port is required",
            )

        timeout = definition.timeout_seconds
        start_time = time.time()
        error: Optional[str] = None
        status = CheckStatus.UNKNOWN
        message = ""

        try:
            # Use asyncio.wait_for with socket for true async TCP check
            loop = asyncio.get_event_loop()

            async def connect_tcp():
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout,
                )
                writer.close()
                await writer.wait_closed()

            await loop.create_task(connect_tcp())
            response_time = (time.time() - start_time) * 1000

            status = CheckStatus.UP
            message = f"TCP port {port} open in {response_time:.0f}ms"

        except asyncio.TimeoutError:
            response_time = timeout * 1000
            error = f"Timeout after {timeout}s"
            status = CheckStatus.DOWN
            message = f"TCP port {port} timed out"
        except ConnectionRefusedError:
            response_time = (time.time() - start_time) * 1000
            error = "Connection refused"
            status = CheckStatus.DOWN
            message = f"TCP port {port} refused"
        except OSError as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            status = CheckStatus.DOWN
            message = f"TCP port {port} unreachable: {e}"
        except Exception as e:
            response_time = 0
            error = str(e)
            status = CheckStatus.DOWN
            message = f"Unexpected error: {e}"

        return CheckResult(
            target_id=definition.id,
            check_type=self.check_type,
            status=status,
            response_time_ms=response_time,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            message=message,
            details={"host": host, "port": port},
            error=error,
        )
