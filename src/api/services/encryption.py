"""Encryption utilities for sensitive data at rest (SNMP credentials)."""

import os
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional


def _get_fernet() -> Optional[Fernet]:
    """Get Fernet instance from NETOPS_ENCRYPTION_KEY env var."""
    key = os.environ.get("NETOPS_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a string field if encryption is enabled."""
    if value is None:
        return None
    fernet = _get_fernet()
    if not fernet:
        return value
    try:
        encrypted = fernet.encrypt(value.encode())
        return encrypted.decode()
    except Exception:
        return value


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """Decrypt a string field if encryption is enabled."""
    if value is None:
        return None
    fernet = _get_fernet()
    if not fernet:
        return value
    try:
        decrypted = fernet.decrypt(value.encode())
        return decrypted.decode()
    except InvalidToken:
        return value
    except Exception:
        return value


def generate_key() -> str:
    """Generate a new Fernet key for NETOPS_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()
