"""Telegram bot notification channel."""

import httpx
from typing import Any

from .base import NotificationChannel, NotificationMessage


class TelegramNotification(NotificationChannel):
    """Telegram bot notification."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.bot_token = config.get("bot_token", "")
        self.chat_id = config.get("chat_id", "")
        self.parse_mode = config.get("parse_mode", "HTML")
        self.api_url = "https://api.telegram.org/bot"

    def validate_config(self) -> tuple[bool, str]:
        """Validate Telegram configuration."""
        if not self.bot_token:
            return False, "Telegram bot token is required"
        if not self.chat_id:
            return False, "Telegram chat ID is required"
        return True, ""

    async def send(self, message: NotificationMessage) -> bool:
        """Send notification to Telegram."""
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        severity_icon = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(message.severity, "📢")

        text = f"""
{severity_icon} *{message.title}*

{message.message}

*Severity:* {message.severity}
*Type:* {message.alert_type}
""".strip()

        # Convert to HTML format for Telegram
        html_text = f"""
{severity_icon} <b>{message.title}</b>

{message.message}

<b>Severity:</b> {message.severity}
<b>Type:</b> {message.alert_type}
""".strip()

        url = f"{self.api_url}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": html_text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                return response.status_code == 200
        except httpx.HTTPError:
            return False
