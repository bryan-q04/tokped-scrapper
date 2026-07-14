"""Normalize a raw product JSON object into a flat row dict.

Sold count from the search API is a *display label* ("1rb+ terjual", "Terjual 250"),
found in labelGroups at position "integrity". We keep both the raw label and a
best-effort integer so bucketed values are still comparable.
"""
from __future__ import annotations  # allow `int | None` hints on Python 3.9

import re


def clean_price(raw) -> int | None:
    """'Rp1.299.000' -> 1299000."""
    if raw is None:
        return None
    digits = re.sub(r"[^\d]", "", str(raw))
    return int(digits) if digits else None


def extract_sold_label(label_groups) -> str | None:
    if not label_groups:
        return None
    for lg in label_groups:
        pos = (lg.get("position") or "").lower()
        title = (lg.get("title") or "")
        if pos == "integrity" and "terjual" in title.lower():
            return title
    # fallback: any label mentioning "terjual"
    for lg in label_groups:
        title = (lg.get("title") or "")
        if "terjual" in title.lower():
            return title
    return None


def parse_sold_number(label: str | None) -> int | None:
    """'1rb+ terjual' -> 1000, 'Terjual 250' -> 250, '2jt+' -> 2000000."""
    if not label:
        return None
    s = label.lower().replace("terjual", "").replace("+", "").strip()
    m = re.search(r"([\d.,]+)\s*(rb|jt)?", s)
    if not m:
        return None
    # Indonesian format: '.' = thousands separator, ',' = decimal
    num = float(m.group(1).replace(".", "").replace(",", "."))
    unit = m.group(2)
    if unit == "rb":
        num *= 1_000
    elif unit == "jt":
        num *= 1_000_000
    return int(num)


def parse_product(p: dict, context: dict) -> dict:
    """Normalize one SearchProductV5Query product object into a flat row."""
    shop = p.get("shop") or {}
    price = p.get("price") or {}
    tier = shop.get("tier")
    sold_label = extract_sold_label(p.get("labelGroups"))

    # V5 aliases: oldID = numeric id, id = string id. Prefer the numeric one.
    product_id = p.get("oldID") if p.get("oldID") is not None else p.get("id")
    shop_id = shop.get("oldID") if shop.get("oldID") is not None else shop.get("id")

    # price.number is an int (e.g. 30500); fall back to parsing price.text ("Rp30.500").
    price_val = price.get("number") if isinstance(price.get("number"), int) else clean_price(price.get("text"))

    return {
        "keyword": context["keyword"],
        "city": context["city"],
        "rank": context["rank"],
        "product_id": str(product_id) if product_id is not None else None,
        "name": p.get("name"),
        "price": price_val,
        "sold_label": sold_label,
        "sold_count": parse_sold_number(sold_label),
        "sold_count_exact": None,  # filled later from product detail if --exact-sold
        "rating": p.get("rating"),
        "review_count": None,  # not provided by V5 search results
        "shop_id": str(shop_id) if shop_id is not None else None,
        "shop_name": shop.get("name"),
        "shop_city": shop.get("city"),
        "is_official": 1 if tier == 2 else 0,     # tier 2 = Mall / Official Store
        "is_power_badge": 1 if tier == 3 else 0,  # tier 3 = Power Shop
        "product_url": p.get("url"),
        "shop_url": shop.get("url"),
        "scraped_at": context["scraped_at"],
        "scrape_date": context["scrape_date"],
    }
