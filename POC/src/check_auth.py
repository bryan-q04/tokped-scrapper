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


def _search(keyword, fcity, cookie, ua, show_adult):
    payload = build_payload(keyword, 1, rows=60, fcity=fcity, show_adult=show_adult)
    return extract_products(post_graphql(payload, cookie, ua))


def _summarize(products, keyword):
    """Return (total, real_hits, accessory_hits) for the target keyword."""
    excl, _ = load_filters()
    kw = keyword.lower()
    real = accessory = 0
    for p in products:
        name = (p.get("name") or "").lower()
        if kw not in name:
            continue
        if any(t in name for t in excl):
            accessory += 1
        else:
            real += 1
    return len(products), real, accessory


def main():
    ap = argparse.ArgumentParser(description="Prove the scrape is authenticated + age-verified")
    ap.add_argument("--keyword", default="terea")
    ap.add_argument("--city", default="jabodetabek")
    args = ap.parse_args()

    cfg = settings.load_city_ids().get(args.city) or {}
    fcity = cfg.get("fcity")
    if not fcity:
        print(f"no fcity entry for '{args.city}' in config/city_ids.json")
        return

    cookie, ua, src = _resolve_cookie()
    print(f"keyword / city : {args.keyword} @ {args.city} (fcity={fcity})")
    print(f"cookie source  : {src}")
    print(f"cookie length  : {len(cookie)} chars")
    print(f"login markers  : {_login_markers(cookie) or 'NONE FOUND (looks anonymous)'}")
    print("-" * 66)

    runs = [
        ("A  cookie   + show_adult=true ", cookie, True),
        ("B  cookie   + show_adult=false", cookie, False),
        ("C  no cookie+ show_adult=true ", "", True),
    ]
    results = {}
    for label, ck, adult in runs:
        try:
            prods = _search(args.keyword, fcity, ck, ua, adult)
            total, real, acc = _summarize(prods, args.keyword)
            results[label[0]] = real
            print(f"{label} : total={total:3d}  real-{args.keyword}={real:3d}  accessory={acc:3d}")
        except Exception as e:  # noqa: BLE001
            results[label[0]] = None
            print(f"{label} : request failed: {e}")

    print("-" * 66)
    a, c = results.get("A"), results.get("C")
    if not cookie:
        print("VERDICT: no cookie resolved -> scrape is ANONYMOUS. Set TOKPED_COOKIE or the auth service.")
    elif a is None:
        print("VERDICT: the authenticated request errored -> can't tell; see the error above.")
    elif c is not None and a > c:
        print(f"VERDICT: AUTH + AGE GATE OK  -> the cookie surfaces {a - c} more real "
              f"'{args.keyword}' listings than anonymous.")
    elif a == 0 and (c or 0) == 0:
        print("VERDICT: ZERO real listings either way. Either this city has no such sellers "
              "(try --city jabodetabek), OR the account never passed age/KTP verification. "
              "Log in to that account in a browser and confirm TEREA is visible there first.")
    else:
        print("VERDICT: the cookie adds NOTHING over anonymous -> it is NOT a logged-in / "
              "age-verified session. Re-copy TOKPED_COOKIE from a browser tab that is logged in "
              "to the age-verified account, update POC/.env, and re-run.")


if __name__ == "__main__":
    main()
