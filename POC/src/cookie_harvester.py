"""Automatic anti-bot cookie harvesting via Playwright (no login required).

Launches Chromium, visits tokopedia.com + a search page so Cloudflare/Tokopedia
run their JS challenge, then captures the EXACT `cookie` header the browser sends
to gql.tokopedia.com. The cookie is cached with a TTL so we don't re-launch a
browser on every run, and can be force-refreshed when a live request gets blocked.

Playwright is imported lazily inside functions, so importing this module (and
running `--sample`) works even when Playwright isn't installed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from settings import DATA_DIR, get_user_agent

COOKIE_CACHE = DATA_DIR / "cookie_cache.json"
SEARCH_URL = "https://www.tokopedia.com/search?st=product&q={kw}"


def _now():
    return datetime.now(timezone.utc)


def load_cached(max_age_min: int = 30):
    """Return (cookie, user_agent, age_min) if a fresh cache exists, else None."""
    try:
        data = json.loads(COOKIE_CACHE.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["harvested_at"])
        age_min = (_now() - ts).total_seconds() / 60
        if age_min <= max_age_min and data.get("cookie"):
            return data["cookie"], data.get("user_agent") or get_user_agent(), age_min
    except Exception:
        pass
    return None


def save_cached(cookie: str, user_agent: str) -> None:
    COOKIE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_CACHE.write_text(
        json.dumps({
            "cookie": cookie,
            "user_agent": user_agent,
            "harvested_at": _now().isoformat(timespec="seconds"),
        }, indent=2),
        encoding="utf-8",
    )


def harvest(headless: bool = True, keyword: str = "iqos",
            user_agent: str | None = None, timeout_ms: int = 60000):
    """Drive a real browser to obtain a valid cookie. Returns (cookie, user_agent).

    Uses a PERSISTENT profile (data/pw_profile) + light stealth tweaks, so a challenge
    solved once (ideally via --headful) is reused by later headless runs.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from e

    ua = user_agent or get_user_agent()
    profile_dir = DATA_DIR / "pw_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    captured: dict = {}

    with sync_playwright() as pw:
        # Persistent context keeps cf_clearance etc. between runs.
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"],
            user_agent=ua,
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            viewport={"width": 1366, "height": 768},
        )
        # Hide the most obvious automation tell.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.pages[0] if context.pages else context.new_page()

        def on_request(req):
            # Grab the cookie the browser actually sends to the GraphQL host.
            if "gql.tokopedia.com" in req.url and "cookie" not in captured:
                try:
                    headers = req.all_headers()
                except Exception:
                    headers = req.headers
                cookie = headers.get("cookie")
                if cookie:
                    captured["cookie"] = cookie

        page.on("request", on_request)

        if not headless:
            print("  [headful] browser window opened — if a Cloudflare/captcha challenge "
                  "appears, solve it; harvesting continues automatically.")
        try:
            page.goto("https://www.tokopedia.com/",
                      wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(3000)
            page.goto(SEARCH_URL.format(kw=keyword),
                      wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass  # partial load is fine as long as cookies were set
        # Longer settle when headful so a human can pass the challenge.
        page.wait_for_timeout(15000 if not headless else 6000)

        cookie = captured.get("cookie")
        if not cookie:
            # Fallback: assemble from the browser cookie jar (includes HttpOnly).
            jar = context.cookies()
            cookie = "; ".join(
                f"{c['name']}={c['value']}"
                for c in jar if "tokopedia.com" in c.get("domain", "")
            )
        context.close()

    if not cookie:
        raise RuntimeError(
            "Harvest produced no cookie. Headless was likely blocked. Do this once:\n"
            "  python src/cookie_harvester.py --headful   (solve any challenge in the window)\n"
            "then re-run normally — the solved profile is reused for headless runs."
        )
    return cookie, ua


def ensure_cookie(ttl_min: int = 30, headless: bool = True,
                  force: bool = False, keyword: str = "iqos"):
    """Return (cookie, user_agent): reuse a fresh cached cookie or harvest a new one."""
    if not force:
        cached = load_cached(ttl_min)
        if cached:
            cookie, ua, age = cached
            print(f"  using cached cookie (age {age:.0f} min, ttl {ttl_min} min)")
            return cookie, ua
    print("  harvesting fresh cookie via Playwright"
          f" ({'headless' if headless else 'headful'})...")
    cookie, ua = harvest(headless=headless, keyword=keyword)
    save_cached(cookie, ua)
    print(f"  harvested cookie ({len(cookie)} chars) and cached.")
    return cookie, ua


def interactive_login(timeout_ms: int = 300000):
    """Open a HEADFUL browser on the persistent profile for a one-time manual login.

    You complete email/phone + password + OTP + age/KTP verification by hand, then press
    Enter. The persistent profile (data/pw_profile) keeps the logged-in session, so later
    headless harvests reuse it. Run on your HOME machine (residential IP).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run:\n  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from e

    ua = get_user_agent()
    profile_dir = DATA_DIR / "pw_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir), headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            user_agent=ua, locale="id-ID", timezone_id="Asia/Jakarta",
            viewport={"width": 1366, "height": 768},
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://www.tokopedia.com/login",
                      wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        print("\n>>> Browser opened. Log in to Tokopedia and finish age/KTP verification.")
        print(">>> When the account is fully logged in, come back here and press Enter.\n")
        try:
            input()
        except EOFError:
            page.wait_for_timeout(120000)
        context.close()
    print("Profile saved (logged in). You can now serve/harvest the authenticated cookie.")


if __name__ == "__main__":
    # Manual test:  python src/cookie_harvester.py [--headful]
    import sys
    hl = "--headful" not in sys.argv
    c, u = ensure_cookie(ttl_min=0, headless=hl, force=True)
    print(f"\nUA: {u}\nCOOKIE (first 120): {c[:120]}...")
