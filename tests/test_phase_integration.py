"""Phase 1+2+4 integration smoke. Validates wire-up without HTTP auth.

Tests environment profile config, check defaults matrix, trap listener module
shape, and discovery merge behavior at the function level. HTTP auth is
exercised in `tests/migration_smoke.test.sh` against the live stack.
"""

import os

os.environ.setdefault("JWT_SECRET", "integration-test-secret")

from src.collector.config import (
    EnvironmentProfile,
    ENVIRONMENT_PROFILES,
    detect_profile,
    NetOpsConfig,
)
from src.collector.checks.base import DEFAULT_CHECK_INTERVALS, default_interval_for
from src.collector.snmp_trap_listener import SNMPTrapListener, _oid_to_trap_type


def test_environment_profiles_have_required_keys():
    for name, profile in ENVIRONMENT_PROFILES.items():
        assert profile["discovery_full_interval"] > 0
        assert profile["discovery_incremental_interval"] > 0
        assert profile["poll_history_retention_days"] > 0
        assert "ssl" in profile["check_intervals"]
        assert profile["check_intervals"]["ssl"] == 86400


def test_detect_profile_returns_known_name():
    name = detect_profile(50)
    assert name in ENVIRONMENT_PROFILES


def test_netops_config_from_profile():
    cfg = NetOpsConfig.from_profile(EnvironmentProfile.DATACENTER)
    assert isinstance(cfg, NetOpsConfig)
    assert cfg.profile == EnvironmentProfile.DATACENTER
    assert cfg.discovery_full_interval == ENVIRONMENT_PROFILES[EnvironmentProfile.DATACENTER]["discovery_full_interval"]


def test_default_check_intervals_keys():
    expected = {"http", "tcp", "dns", "ping", "ssl"}
    assert expected.issubset(DEFAULT_CHECK_INTERVALS.keys())
    for type_name in expected:
        assert default_interval_for(type_name) > 0
    assert default_interval_for("ssl") == 86400


def test_trap_listener_constructs_and_configures():
    listener = SNMPTrapListener(community="trapnet")
    assert listener.community == "trapnet"
    assert listener._port == 162
    assert listener._bind_host == "0.0.0.0"
    assert listener._rate_limit_per_min == 100
    assert listener._running is False
    listener.configure("127.0.0.1", 1162, "newtrap")
    assert listener._port == 1162
    assert listener.community == "newtrap"


def test_oid_to_trap_type():
    assert _oid_to_trap_type("1.3.6.1.6.3.1.1.5.4") == "link_up"
    assert _oid_to_trap_type("1.3.6.1.6.3.1.1.5.3") == "link_down"
    assert _oid_to_trap_type("1.3.6.1.2.1.1.1.0") is None
