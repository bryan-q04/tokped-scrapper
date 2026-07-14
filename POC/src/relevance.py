"""Shared relevance classification.

A product is RELEVANT (a real IQOS device/consumable, not an accessory or a brand
collision) when its name:
  - contains at least one require_any term (allowlist, e.g. iqos/iluma/heets/bonds), AND
  - contains no exclude_term (denylist of accessory/unrelated words).

Both lists live in config/filters.json. Used by the scraper (to store is_relevant) and by
the report (live re-classification so the JSON can be tuned without rescraping).
"""
from __future__ import annotations

import json

import settings

_CACHE = None


def load_filters():
    try:
        cfg = json.loads((settings.CONFIG_DIR / "filters.json").read_text(encoding="utf-8"))
    except Exception:
        return [], []
    excl = [t.lower() for t in cfg.get("exclude_terms", []) if t]
    req = [t.lower() for t in cfg.get("require_any", []) if t]
    return excl, req


def _filters():
    global _CACHE
    if _CACHE is None:
        _CACHE = load_filters()
    return _CACHE


def is_noise(name: str) -> bool:
    excl, req = _filters()
    n = (name or "").lower()
    if any(t in n for t in excl):
        return True
    if req and not any(t in n for t in req):
        return True
    return False


def is_relevant(name: str) -> bool:
    return not is_noise(name)
