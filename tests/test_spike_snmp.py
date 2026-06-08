"""Contract test: spike_snmp must work against the installed pysnmp.

Regression: the original code passed `(host, 161)` positionally to
`UdpTransportTarget(...)`, which collides with `timeout=` in v7 and
raises `TypeError: AbstractTransportTarget.__init__() got multiple
values for argument 'timeout'`. Every poll then failed and devices
flipped offline on the first tick.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.collector import spike_snmp
from src.collector.spike_snmp import (
    _build_auth,
    _build_auth_v2,
    _get_async,
    _walk_async,
    get_sys_descr_async,
    walk_lldp_neighbors_async,
)


def test_udp_transport_uses_create_classmethod():
    """Ensure _get_async / _walk_async construct the transport via .create()."""
    import inspect
    src = inspect.getsource(_get_async)
    assert "UdpTransportTarget.create" in src, (
        "spike_snmp._get_async must construct the v7 transport via "
        "UdpTransportTarget.create((host, 161), ...) — the old "
        "UdpTransportTarget((host, 161), ...) signature raises "
        "TypeError on pysnmp 7.x"
    )
    src2 = inspect.getsource(_walk_async)
    assert "UdpTransportTarget.create" in src2


def test_oids_wrapped_in_object_type():
    """pysnmp 7.x requires ObjectType(ObjectIdentity(oid)) in varBinds."""
    import inspect
    src = inspect.getsource(_get_async)
    assert "ObjectType(ObjectIdentity" in src
    src2 = inspect.getsource(_walk_async)
    assert "ObjectType(ObjectIdentity" in src2


def test_build_auth_v2c():
    from pysnmp.hlapi.asyncio import CommunityData
    a = _build_auth({"community": "private"})
    assert isinstance(a, CommunityData)


def test_build_auth_v3():
    from pysnmp.hlapi.asyncio import UsmUserData
    a = _build_auth({
        "snmp_version": "3",
        "snmpv3_username": "u",
        "snmpv3_auth_protocol": "SHA",
        "snmpv3_auth_key": "aaaa",
        "snmpv3_priv_protocol": "AES",
        "snmpv3_priv_key": "bbbb",
    })
    assert isinstance(a, UsmUserData)


def test_object_type_and_object_identity_imported():
    """Both ObjectType and ObjectIdentity must be in the module namespace."""
    assert hasattr(spike_snmp, "ObjectType")
    assert hasattr(spike_snmp, "ObjectIdentity")


@pytest.mark.asyncio
async def test_get_async_uses_create(monkeypatch):
    """Run a real call against 127.0.0.1 and verify no TypeError on transport build."""
    transport_mock = None
    captured_kwargs = {}

    class _FakeTransport:
        pass

    real_create = spike_snmp.UdpTransportTarget.create

    async def _spy_create(addr, **kwargs):
        captured_kwargs.update(kwargs)
        captured_kwargs["__addr"] = addr
        return _FakeTransport()

    monkeypatch.setattr(spike_snmp.UdpTransportTarget, "create", _spy_create)

    async def _fake_get_cmd(*args, **kwargs):
        return (None, 0, 0, [])

    monkeypatch.setattr(spike_snmp, "get_cmd", _fake_get_cmd)
    res = await get_sys_descr_async("127.0.0.1", _build_auth_v2("127.0.0.1"))
    assert res is None
    assert captured_kwargs["__addr"] == ("127.0.0.1", 161)
    assert "timeout" in captured_kwargs
    assert "retries" in captured_kwargs
