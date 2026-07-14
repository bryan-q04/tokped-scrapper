"""HTTP transport to Tokopedia's GraphQL endpoint.

Prefers curl_cffi (impersonates a real Chrome TLS/HTTP2 fingerprint, which matters
for getting past bot protection); falls back to plain requests. Neither import is
required to load this module — errors are raised only when an actual live POST is
attempted, so `--sample` mode works with zero third-party packages installed.
"""

GQL_URL = "https://gql.tokopedia.com/graphql/SearchProductV5Query"
PDP_URL = "https://gql.tokopedia.com/graphql/PDPGetLayoutQuery"

# NOTE: the URL path segment must equal the operationName. If the search op ever changes
# (e.g. V6), update GQL_URL and search.OPERATION together.

try:
    from curl_cffi import requests as _cffi
    _HAS_CFFI = True
except Exception:
    _HAS_CFFI = False

try:
    import requests as _requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False


def build_headers(cookie: str, user_agent: str,
                  user_id: str = None, device_id: str = None) -> dict:
    """Mirror the browser's SearchProductV5Query request headers. The identity headers
    Tkpd-Userid + Bd-Device-Id (NOT the cookie alone) are what make Tokopedia return the
    curated logged-in result set; without them the search falls back to a generic set that
    floods 'terea' with the Terea-Homeware brand collision. Defaults pulled from settings."""
    import settings  # lazy so --sample stays stdlib-only
    uid = settings.get_user_id() if user_id is None else user_id
    did = settings.get_device_id() if device_id is None else device_id
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,id;q=0.8",
        "content-type": "application/json",
        "origin": "https://www.tokopedia.com",
        "referer": "https://www.tokopedia.com/",
        "user-agent": user_agent,
        "x-dark-mode": "false",
        "x-device": "desktop-0.0",
        "x-price-center": "true",
        "x-source": "tokopedia-lite",
        "x-tkpd-lite-service": "zeus",
        "x-version": settings.get_x_version(),
        "cookie": cookie or "",
    }
    if uid:
        headers["tkpd-userid"] = uid
    if did:
        headers["bd-device-id"] = did
        headers["bd-web-id"] = did
    return headers


def _post(url: str, payload, headers: dict, timeout: int):
    if _HAS_CFFI:
        resp = _cffi.post(url, json=payload, headers=headers,
                          impersonate="chrome", timeout=timeout)
    elif _HAS_REQUESTS:
        resp = _requests.post(url, json=payload, headers=headers, timeout=timeout)
    else:
        raise RuntimeError(
            "No HTTP client available. Run `pip install -r requirements.txt` "
            "(curl_cffi recommended) before a live scrape."
        )
    resp.raise_for_status()
    return resp.json()


def post_graphql(payload, cookie: str, user_agent: str, timeout: int = 30,
                 user_id: str = None, device_id: str = None):
    """POST the search payload and return parsed JSON. Raises on HTTP error."""
    return _post(GQL_URL, payload, build_headers(cookie, user_agent, user_id, device_id), timeout)


def post_pdp(payload, cookie: str, user_agent: str, referer: str, timeout: int = 30):
    """POST a product-detail (PDPGetLayoutQuery) payload; referer = product URL."""
    headers = build_headers(cookie, user_agent)
    headers["x-device"] = "desktop"
    headers["referer"] = referer
    return _post(PDP_URL, payload, headers, timeout)
