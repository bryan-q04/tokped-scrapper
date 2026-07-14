"""VPS-side client: fetch the authenticated cookie from the local auth service.

The auth service runs on your HOME machine (residential IP) behind a private tunnel
(Tailscale/SSH). The runner calls it to get the current logged-in cookie, then scrapes.
Stdlib-only (urllib) so the runner needs no extra deps for this path.
"""
from __future__ import annotations

import json
import urllib.request

# The hostname is proxied through Cloudflare; its Bot Fight Mode / WAF blocks the default
# "Python-urllib/x.y" User-Agent from datacenter IPs with a 403 before the request reaches the
# tunnel. Present as a normal browser so the auth call gets through.
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _headers(token: str) -> dict:
    h = {"User-Agent": _BROWSER_UA, "Accept": "application/json, text/plain, */*"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_credential(base_url: str, token: str = "", timeout: int = 15):
    """GET {base_url}/cred -> (cookie, user_agent). Raises on HTTP/network error."""
    req = urllib.request.Request(base_url.rstrip("/") + "/cred", headers=_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("cookie", ""), data.get("user_agent", "")


def trigger_refresh(base_url: str, token: str = "", timeout: int = 90):
    """POST {base_url}/refresh -> ask the auth service to re-harvest a fresh cookie."""
    req = urllib.request.Request(base_url.rstrip("/") + "/refresh", method="POST",
                                 headers=_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data.get("cookie", ""), data.get("user_agent", "")
