"""Tests for Phase 4 SNMP trap listener (custom BER parser)."""

import asyncio
import pytest

from src.collector import snmp_trap_listener as tl


def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _integer(v: int) -> bytes:
    if v == 0:
        return _tlv(0x02, b"\x00")
    body = v.to_bytes((v.bit_length() + 8) // 8, "big", signed=True)
    return _tlv(0x02, body)


def _oid(components: list[int]) -> bytes:
    if len(components) < 2:
        raise ValueError("OID needs >=2 components")
    body = bytes([components[0] * 40 + components[1]])
    for c in components[2:]:
        # base-128 variable-length
        chunks = []
        x = c
        chunks.append(x & 0x7F)
        x >>= 7
        while x:
            chunks.append((x & 0x7F) | 0x80)
            x >>= 7
        body += bytes(reversed(chunks))
    return _tlv(0x06, body)


def _octet_string(b: bytes) -> bytes:
    return _tlv(0x04, b)


def _ipaddress(a: bytes) -> bytes:
    return _tlv(0x40, a)


def _sequence(body: bytes) -> bytes:
    return _tlv(0x30, body)


def _pdu(tag: int, body: bytes) -> bytes:
    return _tlv(tag, body)


def _varbind(oid_body: bytes, value: bytes) -> bytes:
    return _tlv(0x30, oid_body + value)


def _build_linkup_trap(
    community: bytes = b"public",
    if_index: int = 5,
    if_descr: str = "GigabitEthernet0/1",
) -> bytes:
    trap_oid = _oid([1, 3, 6, 1, 6, 3, 1, 1, 5, 4])  # linkUp
    ifindex_oid = _oid([1, 3, 6, 1, 2, 1, 2, 2, 1, 1, if_index])
    ifdescr_oid = _oid([1, 3, 6, 1, 2, 1, 2, 2, 1, 2, if_index])
    varbinds = _sequence(
        _varbind(trap_oid, _oid([1, 3, 6, 1, 2, 1, 2, 1, 0]))
        + _varbind(ifindex_oid, _integer(if_index))
        + _varbind(ifdescr_oid, _octet_string(if_descr.encode()))
    )
    pdu = _pdu(0xA7, _integer(1) + _integer(0) + _integer(0) + varbinds)
    msg = _sequence(_integer(1) + _octet_string(community) + pdu)
    return msg


def test_linkup_trap_parses_correctly():
    """Custom BER parser extracts source_ip, trap_type, if_index, if_descr."""
    listener = tl.SNMPTrapListener(community="public")
    data = _build_linkup_trap(if_index=12, if_descr="eth0")
    trap = listener._parse_trap(data, ("10.0.0.5", 12345))

    assert trap is not None
    assert trap["source_ip"] == "10.0.0.5"
    assert trap["trap_type"] == "link_up"
    assert trap["if_index"] == 12
    assert trap["if_descr"] == "eth0"
    assert trap["trap_oid"].endswith(".4")


def test_linkdown_trap_parses_correctly():
    listener = tl.SNMPTrapListener(community="public")
    data = _build_linkup_trap()
    # Swap the trap OID to linkDown.
    data = data.replace(
        _oid([1, 3, 6, 1, 6, 3, 1, 1, 5, 4]),
        _oid([1, 3, 6, 1, 6, 3, 1, 1, 5, 3]),
        1,
    )
    trap = listener._parse_trap(data, ("10.0.0.5", 12345))
    assert trap is not None
    assert trap["trap_type"] == "link_down"


def test_unknown_oid_returns_none():
    listener = tl.SNMPTrapListener(community="public")
    data = _build_linkup_trap()
    # Replace trap OID with coldStart (1.3.6.1.6.3.1.1.5.1)
    data = data.replace(
        _oid([1, 3, 6, 1, 6, 3, 1, 1, 5, 4]),
        _oid([1, 3, 6, 1, 6, 3, 1, 1, 5, 1]),
        1,
    )
    assert listener._parse_trap(data, ("10.0.0.5", 12345)) is None


def test_community_mismatch_returns_none():
    listener = tl.SNMPTrapListener(community="private")
    data = _build_linkup_trap(community=b"public")
    assert listener._parse_trap(data, ("10.0.0.5", 12345)) is None


def test_malformed_bytes_does_not_raise():
    listener = tl.SNMPTrapListener(community="public")
    # Garbage
    assert listener._parse_trap(b"\x00\x01\x02", ("x", 1)) is None
    # Empty
    assert listener._parse_trap(b"", ("x", 1)) is None


def test_rate_limit_drops_excess():
    """101st trap from same IP in 60s is dropped."""
    listener = tl.SNMPTrapListener(community="public")
    for i in range(100):
        assert listener._check_rate("10.0.0.1") is True
    assert listener._check_rate("10.0.0.1") is False


def test_rate_window_evicts_expired_entries():
    """Bounded memory: expired entries get cleaned up.

    Without the eviction loop, the dict would grow forever as
    spoofed source IPs (UDP) are added.
    """
    import time
    listener = tl.SNMPTrapListener(community="public")
    listener._rate_window["1.2.3.4"] = [time.time() - 120]  # expired
    listener._rate_window["5.6.7.8"] = [time.time()]          # fresh
    assert len(listener._rate_window) == 2
    listener._evict_rate_window()
    assert "1.2.3.4" not in listener._rate_window
    assert "5.6.7.8" in listener._rate_window
    assert len(listener._rate_window) == 1


def test_oid_to_trap_type():
    assert tl._oid_to_trap_type("1.3.6.1.6.3.1.1.5.4") == "link_up"
    assert tl._oid_to_trap_type("1.3.6.1.6.3.1.1.5.3") == "link_down"
    assert tl._oid_to_trap_type("1.3.6.1.6.3.1.1.5.1") is None
