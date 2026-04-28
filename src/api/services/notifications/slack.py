"""Slack webhook notification channel."""

import httpx
from typing import Any

from .base import NotificationChannel, NotificationMessage


class SlackNotification(NotificationChannel):
    """Slack incoming webhook notification."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.webhook_url = config.get("webhook_url", "")
        self.channel = config.get("channel", "#alerts")
        self.username = config.get("username", "NetOps Bot")
        self.icon_emoji = config.get("icon_emoji", ":robot_face:")

    def validate_config(self) -> tuple[bool, str]:
        """Validate Slack configuration."""
        if not self.webhook_url:
            return False, "Slack webhook URL is required"
        if not self.webhook_url.startswith("https://hooks.slack.com/"):
            return False, "Invalid Slack webhook URL format"
        return True, ""

    async def send(self, message: NotificationMessage) -> bool:
        """Send notification to Slack."""
        if not self.enabled or not self.webhook_url:
            return False

        color = {
            "info": "#36a64f",
            "warning": "#ff9800",
            "error": "#ff0000",
            "critical": "#8b0000",
        }.get(message.severity, "#808080")

        payload = {
            "channel": self.channel,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [
                {
                    "color": color,
                    "title": message.title,
                    "text": message.message,
                    "fields": [
                        {"title": "Severity", "value": message.severity, "short": True},
                        {"title": "Type", "value": message.alert_type, "short": True},
                    ],
                    "footer": "NetOps Alert",
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                return response.status_code == 200
        except httpx.HTTPError:
            return False
