"""PoC entry point.

Live:    python POC/src/runner.py --pages 2 --auto-cookie
Sample:  python POC/src/runner.py --sample     (offline, no cookie/network needed)

Adds its own dir to sys.path so it runs from any working directory.
Writes a timestamped execution log to data/logs/ and a CSV export to data/.
"""
import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import settings          # noqa: E402
import storage           # noqa: E402
import relevance         # noqa: E402
from extract import parse_product   # noqa: E402
from search import build_payload, extract_products  # noqa: E402

log = logging.getLogger("tokped")


def setup_logging() -> Path:
    """Log INFO+ to console and DEBUG+ to a timestamped file under data/logs/."""
    logdir = settings.DATA_DIR / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = logdir / f"run_{stamp}.log"

    log.setLevel(logging.DEBUG)
    log.handlers.clear()

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    log.addHandler(fh)
    log.addHandler(ch)
    return logfile


def _now():
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d")


def _dump_raw(keyword, city, page, data) -> Path:
    """Save a raw API response so empty/blocked results can be diagnosed offline."""
    d = settings.DATA_DIR / "raw"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{keyword}_{city}_p{page}.json"
    try:
        text = json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        text = repr(data)
    p.write_text(text[:500_000], encoding="utf-8")
    return p


def _graphql_errors(data):
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0].get("errors")
    if isinstance(data, dict):
        return data.get("errors")
    return None


def _rows_from_products(products, keyword, city, scraped_at, scrape_date, rank_offset=0):
    rows = []
    for i, p in enumerate(products):
        ctx = {
            "keyword": keyword, "city": city, "rank": rank_offset + i + 1,
            "scraped_at": scraped_at, "scrape_date": scrape_date,
        }
        row = parse_product(p, ctx)
        row["is_relevant"] = 1 if relevance.is_relevant(row.get("name") or "") else 0
        rows.append(row)
    return rows


def _add_exact_sold(rows, cookie, ua, args):
    """For the top-N ranked rows, replace bucketed sold with the exact PDP number."""
    from product_detail import fetch_count_sold

    for r in rows:
        if r["rank"] > args.exact_top or not r.get("product_url"):
            continue
        exact = fetch_count_sold(r["product_url"], cookie, ua)
        if exact is not None:
            r["sold_count_exact"] = exact
        time.sleep(args.delay * 0.5 + random.uniform(0, args.delay * 0.5))


def _resolve_cookie(args):
    """Cookie source: explicit env var > local auth-service cred API > Playwright auto-harvest."""
    env_cookie = settings.get_cookie()
    if env_cookie and not args.refresh_cookie:
        return env_cookie, settings.get_user_agent()
    cred_url = settings.get_cred_url()
    if cred_url:
        from credential import fetch_credential
        try:
            cookie, ua = fetch_credential(cred_url, settings.get_cred_token())
            if cookie:
                log.info("credential: fetched from auth service %s", cred_url)
                return cookie, ua or settings.get_user_agent()
            log.warning("credential: auth service returned an empty cookie")
        except Exception as e:
            log.warning("credential: fetch from %s failed: %s", cred_url, e)
    if args.auto_cookie or args.refresh_cookie:
        from cookie_harvester import ensure_cookie
        return ensure_cookie(ttl_min=args.cookie_ttl, headless=not args.headful,
                             force=args.refresh_cookie, keyword=args.keywords[0])
    return env_cookie, settings.get_user_agent()


def _refresh_cookie(args, keyword):
    """Get a fresh cookie from the active source (cred API or local Playwright harvest)."""
    cred_url = settings.get_cred_url()
    if cred_url:
        from credential import fetch_credential, trigger_refresh
        try:
            cookie, ua = trigger_refresh(cred_url, settings.get_cred_token())
        except Exception:
            cookie, ua = fetch_credential(cred_url, settings.get_cred_token())
        return cookie, ua or settings.get_user_agent()
    from cookie_harvester import ensure_cookie
    return ensure_cookie(ttl_min=0, headless=not args.headful, force=True, keyword=keyword)


def _resolve_category(args):
    """Map --category (name in category_ids.json, literal sc id, or 'none') to an sc value."""
    val = (args.category or "").strip()
    if val.lower() in ("none", "off", "all", ""):
        return None
    return settings.load_category_ids().get(val, val)


def run_live(args, conn):
    from client import post_graphql   # imported here so --sample needs no HTTP libs

    scraped_at, scrape_date = _now()
    if args.reset_today:
        d = storage.delete_scrape_date(conn, scrape_date)
        log.info("reset-today: cleared %d existing rows for %s", d, scrape_date)

    cookie, ua = _resolve_cookie(args)
    # An age-restricted (TEREA) scrape is meaningless without auth, so --show-adult implies it.
    require_cookie = args.require_cookie or args.show_adult
    if not cookie:
        if require_cookie:
            log.error("!! Aborting: a cookie is required (--require-cookie / --show-adult) but none "
                      "was available. Fix the auth service (TOKPED_CRED_URL) and retry.")
            raise SystemExit(3)
        log.warning("!! No cookie available. Set TOKPED_COOKIE in .env or pass --auto-cookie. "
                    "Trying anyway; expect a block.")
    if args.exclude_official:
        log.info("exclude-official: dropping official-store rows before storing")

    category = _resolve_category(args)
    log.info("category filter: %s", f"sc={category}" if category else "none (all categories)")
    cap = args.pages if args.pages else args.max_pages
    if not args.pages:
        log.info("pagination: until no more results (safety cap %d pages/keyword/city)", args.max_pages)

    cities = settings.load_city_ids()
    total = 0

    for keyword in args.keywords:
        for city in args.cities:
            cfg = cities.get(city)
            if not cfg:
                log.warning("  skip: no city_ids entry for '%s'", city)
                continue
            if not cfg.get("verified"):
                log.warning("  ~ '%s' fcity is UNVERIFIED (placeholder) - confirm in Phase 0", city)
            page = 1
            while page <= cap:
                payload = build_payload(keyword, page, rows=args.rows, fcity=cfg["fcity"],
                                        official=args.official_only, category=category,
                                        show_adult=args.show_adult)
                try:
                    data = post_graphql(payload, cookie, ua)
                except Exception as e:
                    log.warning("  [%s/%s p%s] request failed: %s", keyword, city, page, e)
                    if args.auto_cookie or settings.get_cred_url():
                        log.info("  refreshing cookie and retrying once...")
                        cookie, ua = _refresh_cookie(args, keyword)
                        try:
                            data = post_graphql(payload, cookie, ua)
                        except Exception as e2:
                            log.error("  [%s/%s p%s] retry failed: %s", keyword, city, page, e2)
                            break
                    else:
                        break

                errs = _graphql_errors(data)
                if errs:
                    log.warning("  [%s/%s p%s] GraphQL errors: %s",
                                keyword, city, page, json.dumps(errs)[:400])

                products = extract_products(data)
                if not products:
                    raw = _dump_raw(keyword, city, page, data)
                    head = json.dumps(data, ensure_ascii=False)[:400] if data is not None else "None"
                    log.warning("  [%s/%s p%s] 0 products (end/blocked). Raw saved: %s",
                                keyword, city, page, raw)
                    log.debug("  raw head: %s", head)
                    break

                rows = _rows_from_products(products, keyword, city, scraped_at,
                                           scrape_date, rank_offset=(page - 1) * args.rows)
                if args.exclude_official:
                    rows = [r for r in rows if not r["is_official"]]
                if args.exact_sold:
                    _add_exact_sold(rows, cookie, ua, args)
                n = storage.upsert_rows(conn, rows)
                total += n
                log.info("  [%s/%s p%s] %d products stored", keyword, city, page, n)
                for r in rows:
                    log.debug("    seller=%s (id=%s) | %s | Rp%s | sold=%s",
                              r["shop_name"], r["shop_id"], r["name"],
                              r["price"], r["sold_count_exact"] or r["sold_count"])
                if len(products) < args.rows:
                    log.info("  [%s/%s] last page reached (%d < %d) at p%s",
                             keyword, city, len(products), args.rows, page)
                    break
                page += 1
                time.sleep(args.delay + random.uniform(0, args.delay))

    log.info("Stored %d product observations for %s.", total, scrape_date)
    return scrape_date


def run_sample(args, conn):
    log.info("SAMPLE MODE - parsing bundled fixture (no network).")
    scraped_at, scrape_date = _now()
    with open(settings.SAMPLE_FILE, encoding="utf-8") as f:
        data = json.load(f)
    products = extract_products(data)
    rows = _rows_from_products(products, "iqos", "jabodetabek", scraped_at, scrape_date)
    if args.exclude_official:
        rows = [r for r in rows if not r["is_official"]]
        log.info("exclude-official: kept %d non-official rows", len(rows))
    n = storage.upsert_rows(conn, rows)
    log.info("Parsed & stored %d products from the sample.", n)
    for r in rows:
        badge = "OFFICIAL" if r["is_official"] else "seller  "
        log.info("  #%s [%s] %-38s Rp%10s  sold~%s  (%s)",
                 r["rank"], badge, r["name"][:38], f"{r['price']:,}",
                 r["sold_count"], r["sold_label"])

    from product_detail import find_count_sold
    with open(settings.SAMPLE_PDP_FILE, encoding="utf-8") as f:
        pdp = json.load(f)
    exact = find_count_sold(pdp)
    if rows:
        rows[0]["sold_count_exact"] = exact
        storage.upsert_rows(conn, rows)
        log.info("Product-detail EXACT sold for '%s': %s (search label said ~%s)",
                 rows[0]["name"][:32], exact, rows[0]["sold_count"])
    return scrape_date


def print_summary(conn, scrape_date):
    log.info("")
    log.info("=== Official vs non-official (sold totals) for %s ===", scrape_date)
    log.info("%-10s %-13s %5s %11s %11s", "keyword", "type", "#prod", "total_sold", "avg_price")
    for kw, is_off, n, sold, avg in storage.summary_official_vs_not(conn, scrape_date):
        label = "OFFICIAL" if is_off else "non-official"
        log.info("%-10s %-13s %5d %11s %11s", kw, label, n, f"{sold:,}", "Rp" + format(avg or 0, ","))


def main():
    ap = argparse.ArgumentParser(description="Tokopedia IQOS sold-count PoC scraper")
    ap.add_argument("--sample", action="store_true",
                    help="offline demo using tests/sample_response.json")
    ap.add_argument("--keywords", nargs="+", default=settings.DEFAULT_KEYWORDS)
    ap.add_argument("--cities", nargs="+", default=settings.DEFAULT_CITIES)
    ap.add_argument("--pages", type=int, default=None,
                    help="fixed page cap per keyword/city; omit to scrape until no more results")
    ap.add_argument("--max-pages", type=int, default=30,
                    help="safety cap when scraping until exhausted (default 30)")
    ap.add_argument("--category", default=settings.DEFAULT_CATEGORY,
                    help="category filter: a name in category_ids.json, a literal sc id, or 'none'")
    ap.add_argument("--show-adult", action="store_true",
                    help="request age-restricted products (TEREA); needs an authenticated cookie")
    ap.add_argument("--require-cookie", action="store_true",
                    help="abort (exit 3) if no cookie is available instead of scraping anonymously")
    ap.add_argument("--rows", type=int, default=60, help="products per page")
    ap.add_argument("--delay", type=float, default=4.0,
                    help="base delay (s) between requests; jitter added on top")
    ap.add_argument("--official-only", action="store_true",
                    help="apply official-store filter (default: fetch all, tag isOfficial)")
    ap.add_argument("--exclude-official", action="store_true",
                    help="drop official-store rows (keep only non-official sellers)")
    ap.add_argument("--exact-sold", action="store_true",
                    help="fetch precise sold count from product detail (extra requests)")
    ap.add_argument("--exact-top", type=int, default=10,
                    help="with --exact-sold: only fetch exact for top-N per keyword/city")
    ap.add_argument("--auto-cookie", action="store_true",
                    help="auto-harvest the anti-bot cookie via Playwright (no manual paste)")
    ap.add_argument("--refresh-cookie", action="store_true",
                    help="force a fresh Playwright harvest even if a cookie is cached")
    ap.add_argument("--headful", action="store_true",
                    help="show the browser during harvest (use if headless gets blocked)")
    ap.add_argument("--cookie-ttl", type=int, default=30,
                    help="minutes a harvested cookie is reused before re-harvesting")
    ap.add_argument("--reset-today", action="store_true",
                    help="delete today's rows before running (clears stale/sample data)")
    ap.add_argument("--export", default=None,
                    help="CSV export path (default: data/export_<date>.csv)")
    ap.add_argument("--no-export", action="store_true", help="skip the CSV export")
    ap.add_argument("--no-report", action="store_true", help="skip the HTML report")
    ap.add_argument("--db", default=str(settings.DEFAULT_DB))
    args = ap.parse_args()

    logfile = setup_logging()
    log.info("log file: %s", logfile)

    conn = storage.connect(args.db)
    try:
        scrape_date = run_sample(args, conn) if args.sample else run_live(args, conn)
        print_summary(conn, scrape_date)
        if not args.no_export:
            default_name = (f"export_sample_{scrape_date}.csv" if args.sample
                            else f"export_{scrape_date}.csv")
            export_path = args.export or (settings.DATA_DIR / default_name)
            count = storage.export_csv(conn, scrape_date, export_path)
            log.info("Exported %d rows -> %s", count, export_path)
            sellers_path = settings.DATA_DIR / f"sellers_{scrape_date}.csv"
            ns = storage.export_sellers_csv(conn, scrape_date, sellers_path)
            log.info("Sellers of REAL IQOS products -> %s (%d sellers)", sellers_path, ns)
            if not args.no_report:
                from report import generate_report
                html_path = generate_report(export_path)
                log.info("HTML report -> %s", html_path)
    finally:
        conn.close()
    log.info("DB: %s", args.db)


if __name__ == "__main__":
    main()
