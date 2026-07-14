"""Diagnostic: is the scrape actually authenticated AND past the age gate?

`credential: fetched from auth service` in the runner log only proves the runner got a cookie
STRING. It does NOT prove that cookie is a logged-in, age-verified session. This tool proves it
behaviourally: it runs the SAME age-restricted search (default: 'terea') on the same location
three ways and compares how many real TEREA sticks come back:

  A  cookie      + show_adult=true   <- the real scrape
  B  cookie      + show_adult=false  <- isolates the show_adult flag
  C  no cookie   + show_adult=true   <- anonymous baseline (age NOT verified)

If the cookie is a valid adult session, A returns age-restricted sticks that C cannot see.

  python src/check_auth.py                       # terea @ jabodetabek
  python src/check_auth.py --keyword terea --city medan
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import settings                                  # noqa: E402
from client import post_graphql                  # noqa: E402
from relevance import load_filters               # noqa: E402
from search import build_payload, extract_products  # noqa: E402


def _resolve_cookie():
    """Same order the runner uses: explicit env cookie > auth-service cred API."""
    env_cookie = settings.get_cookie()
    if env_cookie:
        return env_cookie, settings.get_user_agent(), "env TOKPED_COOKIE"
    url = settings.get_cred_url()
    if url:
        from credential import fetch_credential
        cookie, ua = fetch_credential(url, settings.get_cred_token())
        return cookie, ua or settings.get_user_agent(), f"auth service {url}"
    return "", settings.get_user_agent(), "none"


def _login_markers(cookie: str):
    """Heuristic only; the A-vs-C behaviour below is the authoritative check."""
    keys = ["_SID_Tokopedia_", "bb_r3c", "DID", "sid_tokopedia"]
    return [k for k in keys if k.lower() in (cookie or "").lower()]


def _search(keyword, fcity, cookie, ua, show_adult, user_id=None, attempts=4):
    """Rebuild the payload each try (fresh unique_id) and retry transient HTTP/2 resets.
    user_id drives BOTH the `user_id` param and the `Tkpd-Userid` header, kept in sync."""
    last = None
    for i in range(attempts):
        payload = build_payload(keyword, 1, rows=60, fcity=fcity, show_adult=show_adult,
                                user_id=user_id)
        try:
            return extract_products(post_graphql(payload, cookie, ua, user_id=user_id))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 + 3 * i)   # 3s, 6s, 9s backoff
    raise last


def _classify_one(name, excl, req, kw):
    """-> (bucket, detail). bucket in {NOKW, EXCL, REAL}; detail = matched term / allow flag."""
    n = (name or "").lower()
    if kw not in n:
        return "NOKW", ""
    hit = next((t for t in excl if t in n), None)
    if hit:
        return "EXCL", hit
    allow = "+allow" if any(t in n for t in req) else "-allow"
    return "REAL", allow


def _summarize(products, keyword):
    """Return (total, real_hits, accessory_hits) for the target keyword."""
    excl, req = load_filters()
    kw = keyword.lower()
    real = accessory = 0
    for p in products:
        bucket, _ = _classify_one(p.get("name"), excl, req, kw)
        if bucket == "EXCL":
            accessory += 1
        elif bucket == "REAL":
            real += 1
    return len(products), real, accessory


def _dump_names(products, keyword):
    """Print every product with its classification so we can eyeball the API result set."""
    excl, req = load_filters()
    kw = keyword.lower()
    for i, p in enumerate(products, 1):
        bucket, detail = _classify_one(p.get("name"), excl, req, kw)
        city = (p.get("shop") or {}).get("city", "")
        tag = {"REAL": "REAL", "EXCL": f"EXCL:{detail}", "NOKW": "no-kw"}[bucket]
        print(f"  {i:2d}. [{tag:14s}] {(p.get('name') or '')[:62]:62s} | {city}")


def main():
    ap = argparse.ArgumentParser(description="Prove that user_id (not cookie/show_adult) is the fix")
    ap.add_argument("--keyword", default="terea")
    ap.add_argument("--city", default="jabodetabek")
    ap.add_argument("--user-id", default=None,
                    help="override user_id (default: TOKPED_USER_ID from .env)")
    args = ap.parse_args()

    cfg = settings.load_city_ids().get(args.city) or {}
    fcity = cfg.get("fcity")
    if not fcity:
        print(f"no fcity entry for '{args.city}' in config/city_ids.json")
        return

    cookie, ua, src = _resolve_cookie()
    uid = args.user_id if args.user_id is not None else settings.get_user_id()
    print(f"keyword / city : {args.keyword} @ {args.city} (fcity={fcity})")
    print(f"cookie source  : {src}  ({len(cookie)} chars, markers={_login_markers(cookie) or 'none'})")
    print(f"user_id in use : {uid or 'EMPTY  <-- set TOKPED_USER_ID in .env'}")
    print(f"device_id      : {settings.get_device_id() or 'EMPTY  <-- set TOKPED_DEVICE_ID in .env'}")
    print("-" * 74)

    # Matrix: isolate user_id (param + Tkpd-Userid header) AND the cookie. Device headers are
    # constant across all three (from TOKPED_DEVICE_ID).
    runs = [
        ("uid EMPTY + cookie   ", "",  cookie),
        ("uid SET   + cookie   ", uid, cookie),
        ("uid SET   + NO cookie", uid, ""),
    ]
    results = {}
    best_products, best_real = [], -1
    for idx, (label, this_uid, this_cookie) in enumerate(runs):
        if idx:
            time.sleep(4)   # space requests so we don't trip the rate limiter
        try:
            prods = _search(args.keyword, fcity, this_cookie, ua, False, user_id=this_uid)
            total, real, acc = _summarize(prods, args.keyword)
            results[label] = real
            if real > best_real:
                best_real, best_products = real, prods
            print(f"[{label}] : total={total:3d}  real-{args.keyword}={real:3d}  accessory={acc:3d}")
        except Exception as e:  # noqa: BLE001
            results[label] = None
            print(f"[{label}] : request failed after retries: {str(e)[:110]}")

    print("-" * 74)
    print(f"page-1 names from the best run (should be clean {args.keyword}):")
    _dump_names(best_products, args.keyword)

    print("-" * 74)
    base = results.get("uid EMPTY + cookie   ")
    setc = results.get("uid SET   + cookie   ")
    setn = results.get("uid SET   + NO cookie")
    if not uid:
        print("VERDICT: no user_id available. Set TOKPED_USER_ID + TOKPED_DEVICE_ID in POC/.env "
              "(from the browser's SearchProductV5Query request) and re-run.")
    elif setc is not None and base is not None and setc > base:
        print(f"VERDICT: FIXED by user_id -> {base} -> {setc} real listings (cookie kept). "
              f"user_id SET + NO cookie = {setn}. I'll thread user_id/device_id into runner + report.")
    elif setn is not None and base is not None and setn > base:
        print(f"VERDICT: FIXED but the COOKIE was hurting -> uid+NO-cookie={setn} beats "
              f"uid+cookie={setc}, baseline={base}. We'll scrape with user_id and drop the cookie.")
    else:
        print("VERDICT: still no lift -> paste this output; we compare device/version headers next.")


if __name__ == "__main__":
    main()
