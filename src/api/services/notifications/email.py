"""Email notification channel via SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Optional

from .base import NotificationChannel, NotificationMessage


class EmailNotification(NotificationChannel):
    """Email notification via SMTP."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.smtp_host = config.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.from_email = config.get("from_email", "")
        self.to_emails = config.get("to_emails", [])
        self.use_tls = config.get("use_tls", True)
        self.use_ssl = config.get("use_ssl", False)

    def validate_config(self) -> tuple[bool, str]:
        """Validate email configuration."""
        if not self.smtp_host:
            return False, "SMTP host is required"
        if not self.username:
            return False, "SMTP username is required"
        if not self.password:
            return False, "SMTP password is required"
        if not self.from_email:
            return False, "Sender email is required"
        if not self.to_emails:
            return False, "At least one recipient email is required"
        return True, ""

    def send(self, message: NotificationMessage) -> bool:
        """Send notification via email (synchronous)."""
        if not self.enabled:
            return False

        if not all([self.smtp_host, self.username, self.password, self.from_email, self.to_emails]):
            return False

        severity_icon = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(message.severity, "📢")

        subject = f"[NetOps] {message.title}"
        body = f"""
{severity_icon} {message.title}

{message.message}

Severity: {message.severity}
Type: {message.alert_type}

---
NetOps Alert System
"""

        msg = MIMEMultipart()
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            if self.use_tls and not self.use_ssl:
                server.starttls()

            server.login(self.username, self.password)
            server.sendmail(self.from_email, self.to_emails, msg.as_string())
            server.quit()
            return True
        except smtplib.SMTPException:
            return False
        except Exception:
            return False
