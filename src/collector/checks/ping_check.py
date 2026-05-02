"""Ping (ICMP) service check executor."""

import asyncio
import platform
import time
from typing import Any, Optional

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus


class PingCheckExecutor(CheckExecutor):
    """Execute ICMP ping checks."""

    @property
    def check_type(self) -> str:
        return "ping"

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate ping check configuration."""
        if "host" not in config:
            return False, "Host is required for ping checks"

        # Validate count if provided
        count = config.get("count", 3)
        if not isinstance(count, int) or count < 1 or count > 10:
            return False, "Count must be between 1 and 10"

        return True, ""

    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute ping check."""
        host = definition.config.get("host", definition.target)
        count = definition.config.get("count", 3)
        timeout = definition.timeout_seconds

        # Determine ping command based on OS
        system = platform.system().lower()

        if system == "windows":
            ping_cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
        else:
            # Linux/macOS
            ping_cmd = ["ping", "-c", str(count), "-W", str(timeout), host]

        start_time = time.time()
        error: Optional[str] = None
        status = CheckStatus.UNKNOWN
        message = ""
        details: dict[str, Any] = {}

        try:
            # Run ping command
            process = await asyncio.create_subprocess_exec(
                *ping_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout + 5,  # Extra buffer for command overhead
            )

            response_time = (time.time() - start_time) * 1000
            output = stdout.decode() + stderr.decode()

            # Parse ping output
            parsed = self._parse_ping_output(output, system)
            details.update(parsed)

            if process.returncode == 0:
                packets_sent = parsed.get("packets_sent", count)
                packets_received = parsed.get("packets_received", 0)
                packet_loss = parsed.get("packet_loss", 0)

                if packets_received > 0:
                    avg_latency = parsed.get("avg_latency", response_time / count)

                    if packet_loss == 0:
                        status = CheckStatus.UP
                        message = f"Ping: {packets_received}/{packets_sent} packets, {avg_latency:.0f}ms avg"
                    elif packet_loss < 50:
                        status = CheckStatus.DEGRADED
                        message = f"Ping: {packet_loss:.0f}% packet loss, {avg_latency:.0f}ms avg"
                    else:
                        status = CheckStatus.DOWN
                        message = f"Ping: High packet loss ({packet_loss:.0f}%)"
                else:
                    status = CheckStatus.DOWN
                    message = "Ping: No response from host"
            else:
                status = CheckStatus.DOWN
                message = f"Ping failed: {output.strip()[:100]}"
                error = output.strip()

        except asyncio.TimeoutError:
            response_time = (timeout + 5) * 1000
            error = "Ping command timed out"
            status = CheckStatus.DOWN
            message = "Ping timed out"
        except FileNotFoundError:
            response_time = 0
            error = "ping command not found"
            status = CheckStatus.DOWN
            message = "ping command not available"
        except Exception as e:
            response_time = 0
            error = str(e)
            status = CheckStatus.DOWN
            message = f"Unexpected error: {e}"

        details["host"] = host
        details["timeout"] = timeout

        return CheckResult(
            target_id=definition.id,
            check_type=self.check_type,
            status=status,
            response_time_ms=response_time,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            message=message,
            details=details,
            error=error,
        )

    def _parse_ping_output(self, output: str, system: str) -> dict[str, Any]:
        """Parse ping command output."""
        result = {
            "packets_sent": 0,
            "packets_received": 0,
            "packet_loss": 0,
            "min_latency": 0,
            "avg_latency": 0,
            "max_latency": 0,
        }

        try:
            lines = output.strip().split("\n")

            if system == "windows":
                # Windows ping output parsing
                for line in lines:
                    if "Packets:" in line:
                        # Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)
                        parts = line.split(",")
                        for part in parts:
                            if "Sent" in part:
                                result["packets_sent"] = int(part.split("=")[1].strip())
                            elif "Received" in part:
                                result["packets_received"] = int(part.split("=")[1].strip())
                            elif "Lost" in part:
                                loss_str = part.split("(")[0].split("=")[1].strip()
                                result["packet_loss"] = float(loss_str.replace("%", ""))

                    if "Approximate round trip times" in line:
                        # Find the next line with timing stats
                        for i, next_line in enumerate(lines[lines.index(line) + 1:], 1):
                            if "ms" in next_line:
                                times = [float(t.replace("ms", "").strip()) for t in next_line.split("=")[1].split(",")]
                                if len(times) >= 3:
                                    result["min_latency"] = times[0]
                                    result["avg_latency"] = times[1]
                                    result["max_latency"] = times[2]
                                break

            else:
                # Linux/macOS ping output parsing
                for line in lines:
                    if "packets transmitted" in line:
                        # 4 packets transmitted, 4 received, 0% packet loss
                        parts = line.split(",")
                        for part in parts:
                            if "packets transmitted" in part:
                                result["packets_sent"] = int(part.split()[0])
                            elif "received" in part:
                                result["packets_received"] = int(part.strip().split()[0])
                            elif "packet loss" in part:
                                result["packet_loss"] = float(part.split()[0].replace("%", ""))

                    if "rtt min/avg/max/mdev" in line or "round-trip min/avg/max" in line:
                        # rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms
                        times_part = line.split("=")[1]
                        times = [float(t.strip()) for t in times_part.split("/")]
                        if len(times) >= 3:
                            result["min_latency"] = times[0]
                            result["avg_latency"] = times[1]
                            result["max_latency"] = times[2]

        except Exception:
            pass  # Return defaults on parse failure

        return result
