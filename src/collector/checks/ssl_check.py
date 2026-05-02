"""SSL certificate check executor."""

import asyncio
import ssl
import socket
import time
from datetime import datetime
from typing import Any, Optional

from .base import CheckDefinition, CheckExecutor, CheckResult, CheckStatus


class SSLCheckExecutor(CheckExecutor):
    """Execute SSL/TLS certificate checks."""

    @property
    def check_type(self) -> str:
        return "ssl"

    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate SSL check configuration."""
        if "host" not in config:
            return False, "Host is required for SSL checks"

        if "port" not in config:
            # Default to 443 if not specified
            pass

        # Validate warning days if provided
        warn_days = config.get("warning_days", 30)
        if not isinstance(warn_days, int) or warn_days < 1:
            return False, "Warning days must be a positive integer"

        return True, ""

    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute SSL check."""
        host = definition.config.get("host", definition.target.split(":")[0] if ":" in definition.target else definition.target)
        port = definition.config.get("port", 443)
        warning_days = definition.config.get("warning_days", 30)
        critical_days = definition.config.get("critical_days", 7)
        timeout = definition.timeout_seconds

        start_time = time.time()
        error: Optional[str] = None
        status = CheckStatus.UNKNOWN
        message = ""
        details: dict[str, Any] = {}

        try:
            # Get SSL certificate info
            loop = asyncio.get_event_loop()
            cert_info = await loop.run_in_executor(
                None,
                self._get_ssl_cert,
                host,
                port,
                timeout,
            )

            response_time = (time.time() - start_time) * 1000

            # Parse certificate dates
            not_before = cert_info["not_before"]
            not_after = cert_info["not_after"]
            issuer = cert_info["issuer"]
            subject = cert_info["subject"]
            version = cert_info["version"]

            now = datetime.utcnow()
            days_until_expiry = (not_after - now).days
            days_since_issued = (now - not_before).days

            details = {
                "host": host,
                "port": port,
                "issuer": issuer,
                "subject": subject,
                "version": version,
                "not_before": not_before.isoformat(),
                "not_after": not_after.isoformat(),
                "days_until_expiry": days_until_expiry,
                "days_since_issued": days_since_issued,
                "serial_number": cert_info.get("serial_number", ""),
            }

            # Check if certificate is expired
            if days_until_expiry < 0:
                status = CheckStatus.DOWN
                message = f"SSL certificate EXPIRED {abs(days_until_expiry)} days ago"
            elif days_until_expiry <= critical_days:
                status = CheckStatus.DOWN
                message = f"SSL certificate expires in {days_until_expiry} days (CRITICAL)"
            elif days_until_expiry <= warning_days:
                status = CheckStatus.DEGRADED
                message = f"SSL certificate expires in {days_until_expiry} days (WARNING)"
            else:
                status = CheckStatus.UP
                message = f"SSL certificate valid for {days_until_expiry} days"

        except asyncio.TimeoutError:
            response_time = timeout * 1000
            error = f"Timeout after {timeout}s"
            status = CheckStatus.DOWN
            message = "SSL handshake timed out"
        except ssl.SSLCertVerificationError as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            status = CheckStatus.DOWN
            message = f"SSL certificate verification failed: {e}"
        except socket.timeout:
            response_time = timeout * 1000
            error = "Connection timed out"
            status = CheckStatus.DOWN
            message = "SSL connection timed out"
        except socket.gaierror as e:
            response_time = 0
            error = f"DNS resolution failed: {e}"
            status = CheckStatus.DOWN
            message = "Could not resolve host"
        except ConnectionRefusedError:
            response_time = 0
            error = "Connection refused"
            status = CheckStatus.DOWN
            message = f"Port {port} refused"
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

    def _get_ssl_cert(self, host: str, port: int, timeout: int) -> dict[str, Any]:
        """Get SSL certificate information (runs in executor)."""
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cert_binary = ssock.getpeercert(binary_form=True)

                # Parse certificate dates
                not_before = datetime.strptime(cert["notBefore"], "%b %d %H:%M:%S %Y %Z")
                not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")

                # Parse issuer and subject
                issuer = ", ".join([f"{k}={v}" for item in cert["issuer"] for k, v in item])
                subject = ", ".join([f"{k}={v}" for item in cert["subject"] for k, v in item])

                # Get serial number
                import hashlib
                serial_number = hashlib.sha256(cert_binary).hexdigest()[:32] if cert_binary else ""

                return {
                    "not_before": not_before,
                    "not_after": not_after,
                    "issuer": issuer,
                    "subject": subject,
                    "version": cert.get("version", "unknown"),
                    "serial_number": serial_number,
                }
