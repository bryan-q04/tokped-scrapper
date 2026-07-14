"""Builds the SearchProductV5Query request payload and extracts the product list.

The `params` variable is a URL-encoded query string, matching what tokopedia.com sends.
Key knobs: q (keyword), page/start/rows (pagination), fcity (location filter),
shop_tier (2 = official-store-only), ob (sort; 23 = best match / default).
"""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

from query import SEARCH_QUERY

OPERATION = "SearchProductV5Query"


def build_params(keyword: str, page: int, rows: int = 60,
                 fcity: str | None = None, shop_tier: str | None = None,
                 sc: str | None = None, show_adult: bool = False,
                 ob: str = "23", user_city_id: str = "176",
                 user_id: str = "", user_district_id: str = "",
                 user_warehouse_id: str = "0") -> str:
    start = (page - 1) * rows
    params = {
        "device": "desktop",
        "enter_method": "normal_search",
        "l_name": "sre",
        "navsource": "",
        "ob": ob,                       # 23 = Paling Sesuai (default sort)
        "page": page,
        "q": keyword,
        "related": "true",
        "rows": rows,
        "safe_search": "false",
        "sc": sc or "",                 # category filter (Tokopedia category id)
        "scheme": "https",
        "shipping": "",
        "show_adult": "true" if show_adult else "false",  # not the age gate — user_id is (see below)
        "source": "search",
        "srp_component_id": "04.06.00.00",   # matches the desktop normal-search surface
        "srp_page_id": "",
        "srp_page_title": "",
        "st": "product",
        "start": start,
        "topads_bucket": "true",
        "unique_id": uuid.uuid4().hex,
        "user_addressId": "",
        "user_cityId": user_city_id,
        "user_districtId": user_district_id,
        # user_id is the real differentiator: with the logged-in account id the search returns
        # the curated result set (real TEREA); empty => generic search flooded with the
        # "Terea Homeware" brand collision. Set TOKPED_USER_ID in .env.
        "user_id": user_id,
        "user_lat": "",
        "user_long": "",
        "user_postCode": "",
        "user_warehouseId": user_warehouse_id,
        "variants": "",
        "warehouses": "",
    }
    if fcity:
        params["fcity"] = fcity           # location filter (comma-separated city IDs)
    if shop_tier:
        params["shop_tier"] = shop_tier   # "2" = Mall/Official Store only
    return urlencode(params)


def build_payload(keyword: str, page: int, rows: int = 60,
                  fcity: str | None = None, official: bool = False,
                  category: str | None = None, show_adult: bool = False,
                  user_id: str | None = None, user_district_id: str | None = None,
                  user_warehouse_id: str | None = None) -> list:
    import settings  # lazy so --sample stays stdlib-only
    shop_tier = "2" if official else None
    params = build_params(
        keyword, page, rows=rows, fcity=fcity, shop_tier=shop_tier, sc=category,
        show_adult=show_adult,
        user_id=settings.get_user_id() if user_id is None else user_id,
        user_district_id=settings.get_district_id() if user_district_id is None else user_district_id,
        user_warehouse_id=settings.get_warehouse_id() if user_warehouse_id is None else user_warehouse_id,
    )
    return [{
        "operationName": OPERATION,
        "variables": {"params": params},
        "query": SEARCH_QUERY,
    }]


def extract_products(response_json) -> list:
    """Dig products out of the V5 response; return [] on any shape mismatch."""
    try:
        return response_json[0]["data"]["searchProductV5"]["data"]["products"] or []
    except (KeyError, IndexError, TypeError):
        return []
