"""Configuration management for NetOps.

Includes Phase 1 environment profiles (homelab / small_business / datacenter)
with per-tier interval defaults. Profile is persisted in app_settings
via migration 008 and read by NetOpsConfig.from_settings() at startup.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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


# ---------------------------------------------------------------------------
# Phase 1: environment profiles
# ---------------------------------------------------------------------------

class EnvironmentProfile(str, Enum):
    """Deployment tier. Determines default poll/retention intervals."""

    HOMELAB = "homelab"
    SMALL_BUSINESS = "small_business"
    DATACENTER = "datacenter"


# Interval matrix (locked in NETOPS_REFRESH_INTERVALS_PLAN.md §3).
# - discovery_full_interval:   seconds between full subnet rescans
# - discovery_incremental:     seconds between incremental probes
# - topology_interval:         seconds between SNMP topology polls
# - check_intervals:           per-type check cadence in seconds
# - poll_history_retention_days: days of poll_history to keep
# - max_devices:               upper bound of this profile's expected
#                               device count (used by detect_profile)
ENVIRONMENT_PROFILES: dict[EnvironmentProfile, dict] = {
    EnvironmentProfile.HOMELAB: {
        "topology_interval": 30,
        "discovery_full_interval": 21600,        # 6h
        "discovery_incremental_interval": 900,    # 15m
        "check_intervals": {
            "ping": 60,
            "http": 60,
            "tcp": 60,
            "dns": 300,
            "ssl": 86400,                          # 24h
        },
        "poll_history_retention_days": 7,
        "max_devices": 15,
    },
    EnvironmentProfile.SMALL_BUSINESS: {
        "topology_interval": 60,
        "discovery_full_interval": 7200,         # 2h
        "discovery_incremental_interval": 600,    # 10m
        "check_intervals": {
            "ping": 30,
            "http": 60,
            "tcp": 60,
            "dns": 300,
            "ssl": 86400,
        },
        "poll_history_retention_days": 14,
        "max_devices": 80,
    },
    EnvironmentProfile.DATACENTER: {
        "topology_interval": 60,
        "discovery_full_interval": 3600,         # 1h
        "discovery_incremental_interval": 300,    # 5m
        "check_intervals": {
            "ping": 30,
            "http": 60,
            "tcp": 60,
            "dns": 300,
            "ssl": 86400,
        },
        "poll_history_retention_days": 30,
        "max_devices": None,                      # unlimited
    },
}


def detect_profile(device_count: int) -> EnvironmentProfile:
    """Guess the deployment profile from current device count.

    homelab       <= 15
    small_business <= 80
    datacenter    > 80
    """
    if device_count <= ENVIRONMENT_PROFILES[EnvironmentProfile.HOMELAB]["max_devices"]:
        return EnvironmentProfile.HOMELAB
    if device_count <= ENVIRONMENT_PROFILES[EnvironmentProfile.SMALL_BUSINESS]["max_devices"]:
        return EnvironmentProfile.SMALL_BUSINESS
    return EnvironmentProfile.DATACENTER


@dataclass
class NetOpsConfig:
    """Runtime configuration loaded from app_settings.

    The `profile` field is the Phase 1 environment profile. Defaults
    to HOMELAB if app_settings has no profile row yet.
    """

    profile: EnvironmentProfile = EnvironmentProfile.HOMELAB
    topology_interval: int = 30
    discovery_full_interval: int = 21600
    discovery_incremental_interval: int = 900
    check_intervals: dict[str, int] = field(default_factory=dict)
    poll_history_retention_days: int = 7

    @classmethod
    def from_profile(cls, profile: EnvironmentProfile) -> "NetOpsConfig":
        defaults = ENVIRONMENT_PROFILES[profile]
        return cls(
            profile=profile,
            topology_interval=defaults["topology_interval"],
            discovery_full_interval=defaults["discovery_full_interval"],
            discovery_incremental_interval=defaults["discovery_incremental_interval"],
            check_intervals=dict(defaults["check_intervals"]),
            poll_history_retention_days=defaults["poll_history_retention_days"],
        )

    @classmethod
    def from_settings(cls, settings: dict) -> "NetOpsConfig":
        """Build a config from the app_settings 'config' JSON blob.

        Honors any of the Phase 1 keys: profile, topology_interval,
        discovery_full_interval, discovery_incremental_interval,
        check_intervals, poll_history_retention_days. Missing keys
        fall back to the homelab defaults.
        """
        try:
            profile_str = settings.get("profile", "homelab")
            profile = EnvironmentProfile(profile_str)
        except ValueError:
            profile = EnvironmentProfile.HOMELAB

        defaults = ENVIRONMENT_PROFILES[profile]
        return cls(
            profile=profile,
            topology_interval=int(
                settings.get("topology_interval", defaults["topology_interval"])
            ),
            discovery_full_interval=int(
                settings.get(
                    "discovery_full_interval",
                    defaults["discovery_full_interval"],
                )
            ),
            discovery_incremental_interval=int(
                settings.get(
                    "discovery_incremental_interval",
                    defaults["discovery_incremental_interval"],
                )
            ),
            check_intervals=dict(
                settings.get("check_intervals", defaults["check_intervals"])
            ),
            poll_history_retention_days=int(
                settings.get(
                    "poll_history_retention_days",
                    defaults["poll_history_retention_days"],
                )
            ),
        )
