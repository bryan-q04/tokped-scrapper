"""Configuration loading: paths, cookie, user-agent, city IDs.

Kept dependency-light so that `--sample` mode runs on the standard library alone
(python-dotenv is optional; only needed to auto-load .env for live runs).
"""
import json
import os
from pathlib import Path

POC_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = POC_ROOT / "config"
DATA_DIR = POC_ROOT / "data"
DEFAULT_DB = DATA_DIR / "tokped.db"
SAMPLE_FILE = POC_ROOT / "tests" / "sample_response.json"
SAMPLE_PDP_FILE = POC_ROOT / "tests" / "sample_pdp.json"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# POC scope defaults (IQOS official store vs non-official sellers benchmark)
# "iqos"+"iluma" (broad) catch the real products incl. TEREA packs (names contain iqos/iluma);
# a bare "terea" keyword just floods with unrelated Terea-Homeware — the allowlist in
# config/filters.json (require_any) is what isolates real products at report time.
DEFAULT_KEYWORDS = ["iqos", "iluma"]
DEFAULT_CITIES = ["jabodetabek", "bandung", "medan", "surabaya"]
DEFAULT_CATEGORY = "none"  # category filter hurts recall (drops real products in other cats)


def _load_dotenv():
    """Best-effort .env load; silently skipped if python-dotenv isn't installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv(POC_ROOT / ".env")
    except Exception:
        pass


_load_dotenv()


def get_cookie() -> str:
    return os.environ.get("TOKPED_COOKIE", "").strip()


def get_user_agent() -> str:
    return os.environ.get("TOKPED_USER_AGENT", "").strip() or DEFAULT_UA


def get_cred_url() -> str:
    """Base URL of the local auth service (e.g. http://home-tailnet:8765). Empty = disabled."""
    return os.environ.get("TOKPED_CRED_URL", "").strip()


def get_cred_token() -> str:
    return os.environ.get("TOKPED_CRED_TOKEN", "").strip()


def load_city_ids() -> dict:
    """Return {city_name: {"fcity": "...", "verified": bool}} from config."""
    with open(CONFIG_DIR / "city_ids.json", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_category_ids() -> dict:
    """Return {category_name: sc_id_string} from config."""
    with open(CONFIG_DIR / "category_ids.json", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}
