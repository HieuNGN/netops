"""Tests for notification channels."""

import pytest
from src.api.services.notifications.base import NotificationChannel, NotificationMessage
from src.api.services.notifications.webhook import WebhookNotification
from src.api.services.notifications.telegram import TelegramNotification
from src.api.services.notifications.whatsapp import WhatsAppNotification
from src.api.services.notifications.slack import SlackNotification
from src.api.services.notifications.email import EmailNotification


class TestNotificationMessage:
    """Tests for NotificationMessage dataclass."""

    def test_create_message(self):
        """Test creating a notification message."""
        msg = NotificationMessage(
            title="Test Alert",
            message="Test message content",
            severity="warning",
            alert_type="device_down",
        )

        assert msg.title == "Test Alert"
        assert msg.message == "Test message content"
        assert msg.severity == "warning"
        assert msg.alert_type == "device_down"

    def test_message_to_dict(self):
        """Test converting message to dictionary."""
        msg = NotificationMessage(
            title="Test",
            message="Content",
            severity="error",
            alert_type="link_down",
        )

        result = msg.to_dict()
        assert result["title"] == "Test"
        assert result["message"] == "Content"
        assert result["severity"] == "error"
        assert result["alert_type"] == "link_down"

    def test_default_severity(self):
        """Test default severity value."""
        msg = NotificationMessage(title="Test", message="Content")
        assert msg.severity == "info"


class TestWebhookNotification:
    """Tests for WebhookNotification channel."""

    def test_valid_config(self):
        """Test webhook configuration validation."""
        config = {"url": "https://example.com/webhook"}
        channel = WebhookNotification(config)
        valid, error = channel.validate_config()
        assert valid is True
        assert error == ""

    def test_missing_url(self):
        """Test validation fails without URL."""
        channel = WebhookNotification({})
        valid, error = channel.validate_config()
        assert valid is False
        assert "URL is required" in error

    def test_invalid_url_format(self):
        """Test validation fails with invalid URL format."""
        config = {"url": "not-a-url"}
        channel = WebhookNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "must be a valid HTTP" in error

    @pytest.mark.asyncio
    async def test_send_disabled(self):
        """Test send returns False when disabled."""
        config = {"url": "https://example.com/webhook", "enabled": False}
        channel = WebhookNotification(config)
        msg = NotificationMessage(title="Test", message="Content")
        result = await channel.send(msg)
        assert result is False


class TestTelegramNotification:
    """Tests for TelegramNotification channel."""

    def test_valid_config(self):
        """Test Telegram configuration validation."""
        config = {"bot_token": "123:ABC", "chat_id": "456"}
        channel = TelegramNotification(config)
        valid, error = channel.validate_config()
        assert valid is True

    def test_missing_token(self):
        """Test validation fails without bot token."""
        config = {"chat_id": "456"}
        channel = TelegramNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "bot token is required" in error

    def test_missing_chat_id(self):
        """Test validation fails without chat ID."""
        config = {"bot_token": "123:ABC"}
        channel = TelegramNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "chat ID is required" in error


class TestWhatsAppNotification:
    """Tests for WhatsAppNotification channel."""

    def test_valid_config(self):
        """Test WhatsApp configuration validation."""
        config = {
            "account_sid": "AC123",
            "auth_token": "token",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
        }
        channel = WhatsAppNotification(config)
        valid, error = channel.validate_config()
        assert valid is True

    def test_missing_account_sid(self):
        """Test validation fails without Account SID."""
        config = {"auth_token": "token"}
        channel = WhatsAppNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "Account SID is required" in error

    def test_missing_auth_token(self):
        """Test validation fails without auth token."""
        config = {"account_sid": "AC123"}
        channel = WhatsAppNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "Auth Token is required" in error


class TestSlackNotification:
    """Tests for SlackNotification channel."""

    def test_valid_config(self):
        """Test Slack configuration validation."""
        config = {"webhook_url": "https://hooks.slack.com/services/XXX"}
        channel = SlackNotification(config)
        valid, error = channel.validate_config()
        assert valid is True

    def test_missing_webhook_url(self):
        """Test validation fails without webhook URL."""
        channel = SlackNotification({})
        valid, error = channel.validate_config()
        assert valid is False
        assert "webhook URL is required" in error

    def test_invalid_webhook_format(self):
        """Test validation fails with invalid webhook format."""
        config = {"webhook_url": "https://example.com/not-slack"}
        channel = SlackNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "Invalid Slack webhook URL" in error


class TestEmailNotification:
    """Tests for EmailNotification channel."""

    def test_valid_config(self):
        """Test email configuration validation."""
        config = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "test@gmail.com",
            "password": "password",
            "from_email": "test@gmail.com",
            "to_emails": ["recipient@example.com"],
        }
        channel = EmailNotification(config)
        valid, error = channel.validate_config()
        assert valid is True

    def test_missing_from_email(self):
        """Test validation fails without sender email."""
        config = {"smtp_host": "smtp.gmail.com", "username": "test", "password": "pass"}
        channel = EmailNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "Sender email is required" in error

    def test_missing_recipients(self):
        """Test validation fails without recipient emails."""
        config = {
            "smtp_host": "smtp.gmail.com",
            "username": "test",
            "password": "pass",
            "from_email": "test@gmail.com",
        }
        channel = EmailNotification(config)
        valid, error = channel.validate_config()
        assert valid is False
        assert "recipient email is required" in error
