"""DNS service check executor."""

import asyncio
import socket
import time
from typing import Any, Optional

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus


class DNSCheckExecutor(CheckExecutor):
    """Execute DNS resolution checks."""

    @property
    def check_type(self) -> str:
        return "dns"

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate DNS check configuration."""
        if "domain" not in config:
            return False, "Domain is required for DNS checks"

        # Validate record type if provided
        record_type = config.get("record_type", "A")
        valid_types = {"A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "PTR"}
        if record_type not in valid_types:
            return False, f"Invalid record type. Must be one of: {valid_types}"

        return True, ""

    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute DNS check."""
        domain = definition.config.get("domain", definition.target)
        record_type = definition.config.get("record_type", "A")
        dns_server = definition.config.get("dns_server")  # Optional custom DNS server
        expected_ips = definition.config.get("expected_ips")  # Optional expected IPs
        timeout = definition.timeout_seconds

        start_time = time.time()
        error: Optional[str] = None
        status = CheckStatus.UNKNOWN
        message = ""
        details: dict[str, Any] = {}

        try:
            # Use asyncio.getaddrinfo for async DNS resolution
            loop = asyncio.get_event_loop()

            async def resolve_dns():
                if dns_server:
                    # Custom DNS server - use dnspython if available
                    # For now, fall back to system resolver
                    pass

                # Map record types to socket families
                if record_type == "AAAA":
                    family = socket.AF_INET6
                else:
                    family = socket.AF_INET

                result = await loop.getaddrinfo(
                    domain,
                    None,
                    family=family,
                    type=socket.SOCK_STREAM,
                )

                # Extract unique IPs
                ips = list(set([addr[4][0] for addr in result]))
                return ips

            ips = await asyncio.wait_for(resolve_dns(), timeout=timeout)
            response_time = (time.time() - start_time) * 1000

            details = {
                "domain": domain,
                "record_type": record_type,
                "resolved_ips": ips,
                "ip_count": len(ips),
            }

            # Check against expected IPs if configured
            if expected_ips:
                matching_ips = set(ips) & set(expected_ips)
                if matching_ips:
                    status = CheckStatus.UP
                    message = f"DNS resolved {len(ips)} IPs in {response_time:.0f}ms (matched {len(matching_ips)} expected)"
                else:
                    status = CheckStatus.DEGRADED
                    message = f"DNS resolved but IPs don't match expected. Got: {ips}, Expected: {expected_ips}"
            else:
                if ips:
                    status = CheckStatus.UP
                    message = f"DNS resolved {len(ips)} IPs in {response_time:.0f}ms"
                else:
                    status = CheckStatus.DEGRADED
                    message = "DNS resolved but no IPs returned"

        except asyncio.TimeoutError:
            response_time = timeout * 1000
            error = f"Timeout after {timeout}s"
            status = CheckStatus.DOWN
            message = "DNS resolution timed out"
        except socket.gaierror as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            status = CheckStatus.DOWN
            message = f"DNS resolution failed: {e.strerror}"
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
            details=details,
            error=error,
        )
