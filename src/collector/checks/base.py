"""Base class for service checks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class CheckStatus(Enum):
    """Status of a service check."""
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


# Phase 2: per-type default intervals. The SSL default of 24h is
# the locked spec decision (NETOPS_REFRESH_INTERVALS_PLAN §1 Q3):
# SSL certificates rarely change faster than daily, so checking
# more often wastes resources.
DEFAULT_CHECK_INTERVALS: dict[str, int] = {
    "ping": 60,
    "http": 60,
    "tcp": 60,
    "dns": 300,
    "ssl": 86400,  # 24 hours
}


def default_interval_for(check_type: str) -> int:
    """Return the Phase 2 default interval for a check type."""
    return DEFAULT_CHECK_INTERVALS.get(check_type, 60)


@dataclass
class CheckResult:
    """Result of a service check."""
    target_id: str
    check_type: str
    status: CheckStatus
    response_time_ms: float
    timestamp: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class CheckDefinition:
    """Definition of a service check to perform."""
    id: str
    name: str
    check_type: str  # http, tcp, dns, ping, ssl
    target: str  # URL, host:port, domain, etc.
    interval_seconds: int = 60
    timeout_seconds: int = 10
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


class CheckExecutor(ABC):
    """Abstract base class for service check executors."""

    @property
    @abstractmethod
    def check_type(self) -> str:
        """Return the check type this executor handles."""
        pass

    @abstractmethod
    async def execute(self, definition: CheckDefinition) -> CheckResult:
        """Execute a service check and return the result."""
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate check configuration. Returns (valid, error_message)."""
        pass
