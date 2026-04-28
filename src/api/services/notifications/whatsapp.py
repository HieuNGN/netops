"""WhatsApp notification channel via Twilio."""

import httpx
from typing import Any
from urllib.parse import quote

from .base import NotificationChannel, NotificationMessage


class WhatsAppNotification(NotificationChannel):
    """WhatsApp notification via Twilio API."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.account_sid = config.get("account_sid", "")
        self.auth_token = config.get("auth_token", "")
        self.from_number = config.get("from_number", "")
        self.to_number = config.get("to_number", "")
        self.api_url = "https://api.twilio.com/2010-04-01/Accounts"

    def validate_config(self) -> tuple[bool, str]:
        """Validate WhatsApp/Twilio configuration."""
        if not self.account_sid:
            return False, "Twilio Account SID is required"
        if not self.auth_token:
            return False, "Twilio Auth Token is required"
        if not self.from_number:
            return False, "Twilio WhatsApp sender number is required"
        if not self.to_number:
            return False, "Recipient WhatsApp number is required"
        return True, ""

    async def send(self, message: NotificationMessage) -> bool:
        """Send notification via WhatsApp."""
        if not self.enabled:
            return False

        if not all([self.account_sid, self.auth_token, self.from_number, self.to_number]):
            return False

        severity_icon = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(message.severity, "📢")

        body = f"{severity_icon} {message.title}\n\n{message.message}\n\nSeverity: {message.severity}\nType: {message.alert_type}"

        url = f"{self.api_url}/{self.account_sid}/Messages.json"

        # Twilio uses form-encoded data
        data = {
            "From": f"whatsapp:{self.from_number}",
            "To": f"whatsapp:{self.to_number}",
            "Body": body,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, auth=(self.account_sid, self.auth_token)) as client:
                response = await client.post(url, data=data)
                return response.status_code in (200, 201)
        except httpx.HTTPError:
            return False
