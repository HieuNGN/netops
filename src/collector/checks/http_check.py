"""HTTP service check executor."""

import time
from typing import Any, Optional

import httpx

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus


class HTTPCheckExecutor(CheckExecutor):
    """Execute HTTP/HTTPS health checks."""

    @property
    def check_type(self) -> str:
        return "http"

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate HTTP check configuration."""
        if "url" not in config:
            return False, "URL is required for HTTP checks"

        url = config["url"]
        if not url.startswith(("http://", "https://")):
            return False, "URL must start with http:// or https://"

        # Validate expected status codes if provided
        expected_status = config.get("expected_status", [200, 201, 202, 203, 204])
        if not isinstance(expected_status, list):
            expected_status = [expected_status]

        for code in expected_status:
            if not isinstance(code, int) or code < 100 or code > 599:
                return False, f"Invalid HTTP status code: {code}"

        return True, ""

    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute HTTP check."""
        url = definition.config.get("url", definition.target)
        method = definition.config.get("method", "GET").upper()
        expected_status = definition.config.get("expected_status", [200, 201, 202, 203, 204])
        headers = definition.config.get("headers", {})
        body = definition.config.get("body")
        follow_redirects = definition.config.get("follow_redirects", True)
        timeout = definition.timeout_seconds

        if not isinstance(expected_status, list):
            expected_status = [expected_status]

        start_time = time.time()
        error: Optional[str] = None
        status = CheckStatus.UNKNOWN
        message = ""
        details: dict[str, Any] = {}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                    follow_redirects=follow_redirects,
                )

                response_time = (time.time() - start_time) * 1000
                status_code = response.status_code

                details = {
                    "status_code": status_code,
                    "url": str(response.url),
                    "content_length": len(response.content),
                }

                if status_code in expected_status:
                    status = CheckStatus.UP
                    message = f"HTTP {status_code} in {response_time:.0f}ms"
                else:
                    status = CheckStatus.DEGRADED
                    message = f"Unexpected status code: {status_code} (expected: {expected_status})"

        except httpx.TimeoutException as e:
            response_time = timeout * 1000
            error = f"Timeout after {timeout}s"
            status = CheckStatus.DOWN
            message = "Request timed out"
        except httpx.ConnectError as e:
            response_time = 0
            error = str(e)
            status = CheckStatus.DOWN
            message = "Connection failed"
        except httpx.RequestError as e:
            response_time = 0
            error = str(e)
            status = CheckStatus.DOWN
            message = f"Request error: {e}"
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
