"""VPS-side client: fetch the authenticated cookie from the local auth service.

The auth service runs on your HOME machine (residential IP) behind a private tunnel
(Tailscale/SSH). The runner calls it to get the current logged-in cookie, then scrapes.
Stdlib-only (urllib) so the runner needs no extra deps for this path.
"""
from __future__ import annotations

import json
import urllib.request


def fetch_credential(base_url: str, token: str = "", timeout: int = 15):
    """GET {base_url}/cred -> (cookie, user_agent). Raises on HTTP/network error."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/cred",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("cookie", ""), data.get("user_agent", "")


def trigger_refresh(base_url: str, token: str = "", timeout: int = 90):
    """POST {base_url}/refresh -> ask the auth service to re-harvest a fresh cookie."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/refresh", method="POST",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("cookie", ""), data.get("user_agent", "")
