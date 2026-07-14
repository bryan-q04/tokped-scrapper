"""Local auth service - serves the current authenticated Tokopedia cookie to the VPS runner.

Run on your HOME machine (residential IP), behind a PRIVATE tunnel (Tailscale / SSH) - never
expose it publicly, a logged-in cookie == account takeover.

  # 1) one-time interactive login (opens a real browser; you do OTP + age verification):
  python src/auth_service.py --login

  # 2) run the API (serves the cookie, auto-refreshes it in the background):
  TOKPED_AUTH_TOKEN=your-secret python src/auth_service.py --serve --port 8765

Endpoints (all except /health require  Authorization: Bearer <TOKPED_AUTH_TOKEN>):
  GET  /health   -> {"ok": true}
  GET  /cred     -> {"cookie","user_agent","harvested_at"}
  POST /refresh  -> force a re-harvest, returns the new cred
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cookie_harvester as ch  # noqa: E402
import settings                # noqa: E402

_LOCK = threading.Lock()
_CRED = {"cookie": "", "user_agent": "", "harvested_at": ""}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set(cookie, ua):
    with _LOCK:
        _CRED.update(cookie=cookie, user_agent=ua, harvested_at=_now())
    return dict(_CRED)


def _manual_cookie():
    """Re-read POC/.env and return (cookie, ua) if TOKPED_COOKIE is set manually, else (None, None).

    This is the reliable path when Tokopedia's login (OTP / new-device checks) fights the
    automated browser: log in with your normal Chrome, paste its cookie into .env, done.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(settings.POC_ROOT / ".env", override=True)  # pick up edits without restart
    except Exception:
        pass
    cookie = os.environ.get("TOKPED_COOKIE", "").strip()
    return (cookie, settings.get_user_agent()) if cookie else (None, None)


def _refresh(headless=True):
    """Serve a manually-pasted cookie (TOKPED_COOKIE) if present; else harvest via Playwright."""
    cookie, ua = _manual_cookie()
    if cookie:
        return _set(cookie, ua)
    cookie, ua = ch.harvest(headless=headless)
    return _set(cookie, ua)


def _load_cached():
    cached = ch.load_cached(max_age_min=10 ** 9)  # ignore age; just load whatever exists
    if cached:
        cookie, ua, _ = cached
        _set(cookie, ua)


class Handler(BaseHTTPRequestHandler):
    def _authed(self):
        token = os.environ.get("TOKPED_AUTH_TOKEN", "")
        if not token:
            return True  # dev only (no token configured)
        return self.headers.get("Authorization", "") == f"Bearer {token}"

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/cred":
            with _LOCK:
                cred = dict(_CRED)
            if not cred["cookie"]:
                return self._send(503, {"error": "no cookie yet - run --login then --serve"})
            return self._send(200, cred)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/refresh":
            try:
                return self._send(200, _refresh())
            except Exception as e:
                return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass  # quiet


def _bg_refresh(interval_min):
    while True:
        time.sleep(max(60, interval_min * 60))
        try:
            _refresh()
            print(f"[{_now()}] cookie refreshed")
        except Exception as e:
            print(f"[{_now()}] refresh failed: {e}")


def main():
    ap = argparse.ArgumentParser(description="Local Tokopedia auth service")
    ap.add_argument("--login", action="store_true", help="one-time interactive headful login")
    ap.add_argument("--serve", action="store_true", help="run the credential API")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (use tailnet IP to expose)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh-min", type=int, default=45, help="cookie refresh interval (min)")
    args = ap.parse_args()

    if args.login:
        ch.interactive_login()
        return

    if args.serve:
        if not os.environ.get("TOKPED_AUTH_TOKEN"):
            print("WARNING: TOKPED_AUTH_TOKEN not set - the endpoint is UNAUTHENTICATED. Set it.")
        mc, _ = _manual_cookie()
        print("mode:", "manual cookie (TOKPED_COOKIE from .env)" if mc
              else "Playwright harvest from the logged-in profile")
        _load_cached()
        try:
            _refresh()
        except Exception as e:
            print(f"initial harvest failed ({e}); serving cached cookie if any")
        threading.Thread(target=_bg_refresh, args=(args.refresh_min,), daemon=True).start()
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
        print(f"auth service on http://{args.host}:{args.port}  (GET /cred, POST /refresh)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            srv.shutdown()
        return

    ap.print_help()


if __name__ == "__main__":
    main()
