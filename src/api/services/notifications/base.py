"""Base notification channel interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NotificationMessage:
    """Standardized notification message."""

    title: str
    message: str
    severity: str = "info"  # info, warning, error, critical
    alert_type: str = ""  # device_down, device_up, topology_change, link_down
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "alert_type": self.alert_type,
            **self.metadata,
        }


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)

    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """Send notification. Returns True on success."""
        pass

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """Validate channel configuration. Returns (valid, error_message)."""
        pass

    def format_message(self, message: NotificationMessage) -> str:
        """Default message formatting."""
        severity_icon = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(message.severity, "📢")

        return f"{severity_icon} **{message.title}**\n{message.message}"
