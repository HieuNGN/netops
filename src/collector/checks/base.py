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
