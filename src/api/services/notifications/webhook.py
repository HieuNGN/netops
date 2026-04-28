"""Generic webhook notification channel."""

import httpx
from typing import Any

from .base import NotificationChannel, NotificationMessage


class WebhookNotification(NotificationChannel):
    """Generic HTTP webhook notification."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.webhook_url = config.get("url", "")
        self.method = config.get("method", "POST")
        self.headers = config.get("headers", {"Content-Type": "application/json"})
        self.payload_template = config.get("payload_template")

    def validate_config(self) -> tuple[bool, str]:
        """Validate webhook configuration."""
        if not self.webhook_url:
            return False, "Webhook URL is required"
        if not self.webhook_url.startswith(("http://", "https://")):
            return False, "Webhook URL must be a valid HTTP/HTTPS URL"
        return True, ""

    async def send(self, message: NotificationMessage) -> bool:
        """Send notification via webhook."""
        if not self.enabled:
            return False

        if not self.webhook_url:
            return False

        # Build payload
        if self.payload_template:
            # Custom template support could be added here
            payload = self._build_default_payload(message)
        else:
            payload = message.to_dict()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method=self.method,
                    url=self.webhook_url,
                    headers=self.headers,
                    json=payload,
                )
                return response.status_code < 400
        except httpx.HTTPError:
            return False

    def _build_default_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """Build default JSON payload."""
        return {
            "text": message.message,
            "title": message.title,
            "severity": message.severity,
            "alert_type": message.alert_type,
        }
