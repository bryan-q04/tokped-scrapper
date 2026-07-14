"""SQLite persistence. One `observations` table, one row per
(scrape_date, keyword, city, product_id) so re-running the same day is idempotent
and day-over-day sold_count deltas can be computed later.
"""
import csv
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    scrape_date    TEXT NOT NULL,
    scraped_at     TEXT NOT NULL,
    keyword        TEXT NOT NULL,
    city           TEXT NOT NULL,
    rank           INTEGER,
    product_id     TEXT,
    name           TEXT,
    price          INTEGER,
    sold_label       TEXT,
    sold_count       INTEGER,   -- bucketed from search label ("1rb+" -> 1000)
    sold_count_exact INTEGER,   -- precise, from product detail (PDPGetLayoutQuery)
    rating         REAL,
    review_count   INTEGER,
    shop_id        TEXT,
    shop_name      TEXT,
    shop_city      TEXT,
    is_official    INTEGER,
    is_power_badge INTEGER,
    is_relevant    INTEGER,   -- 1 = real IQOS product, 0 = accessory/noise (from filters.json)
    product_url    TEXT,
    shop_url       TEXT,
    UNIQUE(scrape_date, keyword, city, product_id)
);
"""

COLUMNS = [
    "scrape_date", "scraped_at", "keyword", "city", "rank", "product_id",
    "name", "price", "sold_label", "sold_count", "sold_count_exact",
    "rating", "review_count",
    "shop_id", "shop_name", "shop_city", "is_official", "is_power_badge",
    "is_relevant", "product_url", "shop_url",
]


def connect(db_path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    # lightweight migration: add columns introduced after a DB was first created
    have = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
    if "is_relevant" not in have:
        conn.execute("ALTER TABLE observations ADD COLUMN is_relevant INTEGER")
    conn.commit()
    return conn


def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    placeholders = ",".join(["?"] * len(COLUMNS))
    updates = ",".join(f"{c}=excluded.{c}" for c in COLUMNS)
    sql = (
        f"INSERT INTO observations ({','.join(COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(scrape_date, keyword, city, product_id) DO UPDATE SET {updates}"
    )
    conn.executemany(sql, [[r.get(c) for c in COLUMNS] for r in rows])
    conn.commit()
    return len(rows)


def delete_scrape_date(conn: sqlite3.Connection, scrape_date: str) -> int:
    """Remove all rows for a given scrape_date (e.g. to clear stale/sample data)."""
    cur = conn.execute("DELETE FROM observations WHERE scrape_date = ?", (scrape_date,))
    conn.commit()
    return cur.rowcount


def export_csv(conn: sqlite3.Connection, scrape_date: str, path) -> int:
    """Write all rows for a scrape_date to CSV (utf-8-sig so Excel reads it cleanly)."""
    cur = conn.execute(
        f"SELECT {','.join(COLUMNS)} FROM observations WHERE scrape_date = ? "
        f"ORDER BY keyword, city, rank",
        (scrape_date,),
    )
    rows = cur.fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)


SELLER_COLUMNS = ["shop_id", "shop_name", "shop_city", "is_official",
                  "n_products", "total_sold", "sample_products"]


def export_sellers_csv(conn: sqlite3.Connection, scrape_date: str, path,
                       relevant_only: bool = True) -> int:
    """Aggregate REAL-IQOS-product sellers to CSV: one row per seller.

    Products are deduped by product_id first (so a product matched under several keywords
    isn't counted multiple times), then rolled up per seller.
    """
    where_rel = "AND is_relevant = 1" if relevant_only else ""
    cur = conn.execute(
        f"""
        WITH per_product AS (
            SELECT product_id,
                   MAX(shop_id)   AS shop_id,
                   MAX(shop_name) AS shop_name,
                   MAX(shop_city) AS shop_city,
                   MAX(is_official) AS is_official,
                   MAX(name)      AS name,
                   MAX(COALESCE(sold_count_exact, sold_count)) AS sold
            FROM observations
            WHERE scrape_date = ? {where_rel}
            GROUP BY product_id
        )
        SELECT shop_id, shop_name, shop_city, MAX(is_official) AS is_official,
               COUNT(*) AS n_products,
               COALESCE(SUM(sold), 0) AS total_sold,
               GROUP_CONCAT(name, ' | ') AS sample_products
        FROM per_product
        GROUP BY shop_id
        ORDER BY total_sold DESC, n_products DESC
        """,
        (scrape_date,),
    )
    rows = cur.fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(SELLER_COLUMNS)
        for r in rows:
            r = list(r)
            r[-1] = (r[-1] or "")[:300]  # trim sample_products
            w.writerow(r)
    return len(rows)


def summary_official_vs_not(conn: sqlite3.Connection, scrape_date: str) -> list:
    """Return rows: (keyword, is_official, n_products, total_sold, avg_price)."""
    cur = conn.execute(
        """
        SELECT keyword,
               is_official,
               COUNT(*)                AS n_products,
               COALESCE(SUM(COALESCE(sold_count_exact, sold_count)), 0) AS total_sold,
               CAST(AVG(price) AS INTEGER)  AS avg_price
        FROM observations
        WHERE scrape_date = ?
        GROUP BY keyword, is_official
        ORDER BY keyword, is_official DESC
        """,
        (scrape_date,),
    )
    return cur.fetchall()
