"""Host network state: detect, fingerprint, persist.

Tracks the host's currently-attached network (CIDR + gateway) across
restarts. Used by the startup auto-discover and the runtime network
watcher to detect "new network" events.

Fingerprint = `sha256(f"{cidr}|{gateway}")[:16]` (URL-safe, log-friendly).
"""

import hashlib
from typing import Any, Optional

from .host_detect import detect_host_network


def compute_fingerprint(cidr: Optional[str], gateway: Optional[str]) -> Optional[str]:
    if not cidr:
        return None
    raw = f"{cidr.strip().lower()}|{(gateway or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def get_host_state(db_client: Any) -> dict[str, Optional[str]]:
    """Read the previously-saved host network state from app_settings."""
    out: dict[str, Optional[str]] = {
        "host_cidr": None,
        "host_gateway": None,
        "host_fingerprint": None,
        "host_last_seen": None,
    }
    if not hasattr(db_client, "get_setting"):
        return out
    for k in out:
        try:
            v = await db_client.get_setting(k)
            if isinstance(v, str) and v:
                out[k] = v
        except Exception:
            pass
    return out


async def set_host_state(
    db_client: Any,
    cidr: str,
    gateway: Optional[str],
) -> str:
    """Persist the current host network state. Returns the new fingerprint."""
    fp = compute_fingerprint(cidr, gateway) or ""
    if hasattr(db_client, "set_setting"):
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            await db_client.set_setting("host_cidr", cidr)
            if gateway:
                await db_client.set_setting("host_gateway", gateway)
            await db_client.set_setting("host_fingerprint", fp)
            await db_client.set_setting("host_last_seen", now_iso)
        except Exception:
            pass
    return fp


async def detect_and_compare(db_client: Any) -> dict[str, Any]:
    """Detect host network, compare to stored fingerprint.

    Returns:
        {
          "detected": {"host_ip", "cidr", "hostname", "gateway", "interface"},
          "previous": {"host_cidr", "host_gateway", "host_fingerprint", "host_last_seen"},
          "fingerprint": str,
          "changed": bool,
          "first_seen": bool,
        }
    """
    detected = await detect_host_network()
    previous = await get_host_state(db_client)
    fp = compute_fingerprint(detected.get("cidr"), detected.get("gateway"))
    prev_fp = previous.get("host_fingerprint")
    return {
        "detected": detected,
        "previous": previous,
        "fingerprint": fp,
        "changed": bool(fp) and bool(prev_fp) and fp != prev_fp,
        "first_seen": not prev_fp,
    }
