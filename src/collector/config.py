"""Configuration management for NetOps."""

import os
from dataclasses import dataclass


@dataclass
class SNMPConfig:
    """SNMP configuration."""

    host: str = os.getenv("SNMP_HOST", "127.0.0.1")
    community: str = os.getenv("SNMP_COMMUNITY", "public")
    timeout: int = int(os.getenv("SNMP_TIMEOUT", "5"))
    retries: int = int(os.getenv("SNMP_RETRIES", "3"))


@dataclass
class ServerConfig:
    """Server configuration."""

    host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    port: int = int(os.getenv("SERVER_PORT", "8000"))
