"""Auth gating contract for the new Phase 1+4 endpoints.

Pins the auth requirement: any mutating endpoint added without
`Depends(need_auth)` is a bug. This test talks to a LIVE backend
(via BACKEND_URL env var, default http://127.0.0.1:8000) so it
catches real misconfigurations in `src/collector/main.py`.

Mutating endpoints that MUST be auth-gated:
  - PUT /api/config
  - PUT /api/config/profile
  - PUT /api/config/traps
  - POST /discover
  - POST /discover/rescan
  - POST /devices/{id}/stale-action
  - GET /api/checks/defaults
"""

import os
import pytest
import httpx


BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


AUTH_REQUIRED_ENDPOINTS = [
    ("PUT", "/api/config", {}),
    ("PUT", "/api/config/profile", {"profile": "homelab", "confirmado": True}),
    ("PUT", "/api/config/traps", {"port": 1162}),
    ("POST", "/discover", {"network_range": "10.0.0.0/24"}),
    ("POST", "/discover/rescan", {"network_range": "10.0.0.0/24", "mode": "merge"}),
    ("POST", "/devices/abc/stale-action", {"action": "delete"}),
    ("GET", "/api/checks/defaults", None),
]


@pytest.mark.parametrize("method,path,body", AUTH_REQUIRED_ENDPOINTS)
def test_endpoint_requires_auth(method, path, body):
    """Every endpoint below must return 401 without a valid token."""
    with httpx.Client(base_url=BACKEND_URL, timeout=5.0) as c:
        if method == "GET":
            resp = c.get(path)
        elif method == "POST":
            resp = c.post(path, json=body or {})
        elif method == "PUT":
            resp = c.put(path, json=body or {})
        else:
            pytest.fail(f"unsupported method {method}")

    assert resp.status_code == 401, (
        f"{method} {path} should require auth, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )
