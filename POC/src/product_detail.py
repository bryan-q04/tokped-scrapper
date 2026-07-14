"""Fetch the EXACT sold count for a product from its detail page.

Search results only expose a bucketed label ("1rb+ terjual"). The product-detail
GraphQL op (PDPGetLayoutQuery) returns txStats.countSold — the precise number.

`find_count_sold` walks the response recursively for a `countSold` key, so it keeps
working even if Tokopedia nests the field differently than our minimal query assumes.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from query import PDP_QUERY


def parse_product_ref(url: str):
    """https://www.tokopedia.com/{shop}/{product-slug}?... -> (shop, product_key)."""
    if not url:
        return None, None
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, None
    return parts[0], parts[1]


def build_pdp_payload(shop_domain: str, product_key: str) -> list:
    return [{
        "operationName": "PDPGetLayoutQuery",
        "variables": {
            "shopDomain": shop_domain,
            "productKey": product_key,
            "layoutID": "",
            "apiVersion": 1,
        },
        "query": PDP_QUERY,
    }]


def _to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def find_count_sold(obj) -> int | None:
    """Recursively find the first usable `countSold` value in the response."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == "countSold":
                    n = _to_int(v)
                    if n is not None:
                        return n
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def fetch_count_sold(url: str, cookie: str, user_agent: str) -> int | None:
    """Live: resolve a product URL to its exact sold count. Returns None on failure."""
    from client import post_pdp  # imported lazily so sample mode needs no HTTP libs

    shop, key = parse_product_ref(url)
    if not shop or not key:
        return None
    try:
        data = post_pdp(build_pdp_payload(shop, key), cookie, user_agent, referer=url)
    except Exception:
        return None
    return find_count_sold(data)
