# Tokopedia Sold-Count Scraper — Research & Plan

> Goal: Benchmark how many units **non-official sellers** sell per product vs. our
> **IQOS Official Store** listings, by searching a keyword, filtering by location,
> and collecting sold-count data per seller/product.

_Last updated: 2026-07-01_

---

## 1. Business objective

Our IQOS products live under an **Official Store** badge but appear to sell **fewer
units** than competing **non-official sellers**. We want data to prove/quantify this.

Concretely, per keyword we want to answer:

- For a given search keyword (e.g. `"speaker polytron"`), and a given **location filter**
  (e.g. Jakarta), **how many units are sold** by each seller/product?
- How do **official-store** results compare to **non-official-seller** results
  (price, sold count, rating, ranking position)?

### POC scope (first run)

- **Keywords:** `iqos`, `iluma`, `terea`
- **Cities:** `jabodetabek`, `bandung`, `medan`, `surabaya`
- **Both filters per keyword×city:** `official=true` and `official=false` → so we can diff
  our official store vs. the non-official sellers on the same query.
- Run matrix = 3 keywords × 4 cities × 2 official-flags = **24 search runs** (× pagination).

> **Product note:** IQOS/ILUMA are devices; **TEREA are tobacco heat-sticks**. Tobacco/nicotine
> listings are often **restricted** on Tokopedia, so expect `terea` to surface mostly
> accessories, pods holders, or listings using euphemisms/partial names — and possibly fewer
> results than `iqos`/`iluma`. Worth eyeballing the raw results early so the numbers aren't
> misread.

> **Jabodetabek is a metro area, not one city** — it spans Jakarta, Bogor, Depok, Tangerang,
> Bekasi. In `fcity` that's a **list of many city IDs**, not one. We'll map it as a named
> group in `city_ids.json` (see §5).

**Output we need per product row:**

| Field | Example | Notes |
|---|---|---|
| keyword | `speaker polytron` | the search term used |
| rank / position | `7` | ordering in search results |
| product_name | `Speaker Polytron PMA 9300` | |
| price | `450000` | IDR, integer |
| sold_count | `250` or `100+` | bucketed, from search label (see §6) |
| sold_count_exact | `1043` | **key metric** — exact, from product detail (§6) |
| rating | `4.8` | |
| review_count | `120` | |
| shop_name | `Polytron Official` | |
| shop_location | `Jakarta Pusat` | for location analysis |
| is_official | `true` | official store badge |
| is_power_badge | `false` | "Power Merchant Pro" |
| product_url | `https://...` | |
| shop_url | `https://...` | |
| scraped_at | `2026-07-01T10:00Z` | timestamp for daily deltas |

---

## 2. Reference repos reviewed

### A. [hannah2gah/web-scraping-tokopedia](https://github.com/hannah2gah/web-scraping-tokopedia)
- **Method:** Selenium (browser automation) + BeautifulSoup parsing + Pandas → CSV.
- **Env:** Conda, Python ≥3.8, ChromeDriver.
- **Fields:** Penjual (seller), Lokasi (location), Produk, Harga, Rate, Terjual (sold).
- **Config:** driver path, target URL, page range, output filename.

### B. [crypter70/Tokopedia-Scraper](https://github.com/crypter70/Tokopedia-Scraper)
- **Method:** Selenium with JS-enabled selectors + tqdm → CSV & JSON. Last sample data 2023-02-09.
- **Fields:** name, price, location, rating, sold count, product link.
- **Mechanics:** types keyword into search box via XPath, presses Enter, iterates product
  cards by CSS class (e.g. `css-12sieg3`), clicks "Laman berikutnya" (next page) to paginate.

### Verdict on the reference repos
Both are **Selenium + hard-coded CSS/XPath selectors**. That approach still *works
conceptually* but is **fragile and dated**:

- The class names they target (`css-12sieg3`, `prd_link-product-name css-3um8ox`, …) are
  **auto-generated / hashed** and **change frequently** — 2023-era selectors are almost
  certainly broken today.
- Selenium is **slow** (full browser per run) and **easier to bot-detect**.
- They don't demonstrate **location filtering** or **official-store filtering**, which are
  core to our use case.

**We'll borrow their *workflow* (keyword → paginate → extract fields → CSV) but replace the
*transport* with Tokopedia's internal GraphQL search API**, falling back to a headless
browser only if the API path gets blocked.

---

## 3. Approach comparison

| Approach | Speed | Robustness | Effort | Anti-bot risk | Recommendation |
|---|---|---|---|---|---|
| **A. Internal GraphQL API** (`gql.tokopedia.com`) | ★★★ fast | ★★ medium (params drift) | Medium | Medium | **Primary** |
| **B. Selenium / Playwright** (render + parse DOM) | ★ slow | ★ low (hashed classes) | Medium-High | Higher | **Fallback** |
| **C. Playwright to *capture* the GraphQL response** | ★★ | ★★★ | Medium | Lower | **Hybrid (best resilience)** |
| ~~D. Paid 3rd-party API (Apify / ScrapingBee)~~ | ★★★ | ★★★ | Low | None | **Excluded — no paid API (owner decision)** |

**Recommended: start with A (direct GraphQL), and keep C (Playwright-captured GraphQL) as the
resilient fallback if Tokopedia's bot protection blocks the direct call. Paid third-party APIs
are out of scope — everything stays self-hosted and local.**

Rationale: the GraphQL response returns **structured JSON** (no brittle CSS parsing) and
directly includes `shop.isOfficial`, `shop.city`, price, and sold labels — exactly our fields.

---

## 4. Tokopedia GraphQL search API (primary path)

**Endpoint (keyword search):**
```
POST https://gql.tokopedia.com/graphql/SearchProductQueryV4
```
> Note: version suffix has historically moved (V4 → V5). Confirm the current operation name
> by opening tokopedia.com search in Chrome DevTools → Network → filter `graphql`.

**Key query variables (passed inside the `params` string of the GraphQL variables):**

| Param | Meaning | Example |
|---|---|---|
| `q` | keyword | `speaker polytron` |
| `page` | page number | `1` |
| `start` | result offset | `0`, `60`, `120` … |
| `rows` | results per page | `60` |
| `ob` | order by / sort | `0` default, others = price/most-sold (verify codes) |
| `fcity` | **location filter (city IDs)** | `174,175,176,177,178,463` (Jakarta) |
| `official` | **official-store filter** | `true` |
| `pmin` / `pmax` | price range | `100000` / `500000` |
| `condition` | new/used | `1` = new |
| `source` | request source | `search` / `universe` |
| `device` | device | `desktop` |

**Required headers (mimic a real browser — see §7):**
```
content-type: application/json
user-agent:  Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...
origin:      https://www.tokopedia.com
referer:     https://www.tokopedia.com/search?q=<keyword>
x-device:    desktop-0.0
x-source:    tokopedia-lite
x-tkpd-akamai / x-price-center: (may be required)
cookie:      <a fresh session cookie captured from a real visit>
```

**Response path to products:**
```python
resp.json()[0]["data"]["ace_search_product_v4"]["data"]["products"]
```

**Per-product fields available** (from the search response):
`id`, `name`, `url`, `price`, `originalPrice`, `discountPercentage`, `imageUrl`,
`rating`, `countReview`, `categoryName`, `labelGroups[]` (contains the **sold label**),
and `shop { id, name, url, city, isOfficial, isPowerBadge }`.

---

## 5. The location filter (critical for our use case)

Two ways to constrain by location:

1. **`fcity` param** = comma-separated **Tokopedia city IDs**. Example: Jakarta ≈
   `174,175,176,177,178,463`. We need a **city-ID lookup table** — the reliable way to get
   IDs is to apply the location filter on the website UI and read the resulting `fcity`
   value from the request URL / GraphQL variables in DevTools.
2. **`user_cityId`** = the *requesting user's* city (affects shipping/availability ranking),
   not a hard filter. Useful to simulate "a buyer in Jakarta".

**`city_ids.json` for the POC** — map each name to its `fcity` value (fill IDs from DevTools):

```jsonc
{
  "jabodetabek": "174,175,176,177,178,463,164,165,166,167,168,169,151,152,153,154,155,156",
  //             ^ Jakarta(5) + Bogor + Depok + Tangerang + Bekasi — a GROUP of city IDs
  "bandung":     "<bandung city id(s)>",
  "medan":       "<medan city id(s)>",
  "surabaya":    "<surabaya city id(s)>"
}
```

> The IDs above are illustrative — **capture the real values in Phase 0** by ticking each
> city in the site's location filter and reading `fcity` from the request. Jabodetabek is a
> named *group* of several city IDs, so it maps to a comma-joined list, not a single number.

**Action item:** build `city_ids.json` for `jabodetabek`, `bandung`, `medan`, `surabaya`.

---

## 6. Sold-count precision (important caveat)

- The **search API returns a *bucketed / display* sold value**, e.g. `"Terjual 100+"`,
  `"1rb+ terjual"` — found inside `labelGroups` (look for the `integrity` position label).
  Good enough for **relative comparison and ranking**, not exact.
- For a **more exact** count, hit the **product detail** endpoint per product:
  ```
  POST https://gql.tokopedia.com/graphql/PDPGetLayoutQuery
  → basicInfo.txStats.countSold
  ```
  This costs one extra request per product, so only do it for the shortlisted products we
  actually want precise numbers on.
- **Daily deltas** give true velocity: store `countSold` daily and compute
  `sold_today = countSold_today − countSold_yesterday`. This is the most defensible
  "how much do they actually sell" metric for the IQOS comparison.
- **Not every seller exposes sold count** (seller setting) — expect nulls; handle gracefully.

---

## 7. Anti-bot considerations (2026)

Tokopedia sits behind bot protection (Cloudflare-class: TLS/HTTP2 fingerprinting, header
inspection, JS challenges, rate/behavior analysis). To stay under the radar:

- **Realistic headers in the right order** (Accept-Language, Accept-Encoding, Sec-CH-UA,
  User-Agent) + a **fresh cookie** captured from a genuine browser session.
- **Rate limiting & jitter**: randomized delays (e.g. 3–8 s) between requests; no bursts.
- **Rotate** user-agents / proxies (residential ID proxies) if scaling up.
- Consider **`curl_cffi`** (TLS-impersonation) instead of `requests` to match a real browser's
  TLS fingerprint — often the difference between 200 and 403.
- **Fallback = Playwright** (headless Chromium): let the real browser solve challenges, then
  either read the DOM or **intercept the GraphQL response** (approach C) for clean JSON.
- Keep volumes modest and **scrape during off-peak** to reduce footprint.

**Implemented:** cookie handling is automated in `POC/src/cookie_harvester.py` (`--auto-cookie`).
It drives Chromium to pass the challenge, captures the exact cookie the browser sends to
`gql.tokopedia.com`, caches it with a TTL, and re-harvests automatically when a live request
is blocked — no manual paste, no login (the cookie is **anti-bot, not authentication**).

---

## 8. Recommended tech stack (fresh build, 2026)

- **Python 3.12** (3.11+ fine). The reference repos target 3.8; no reason to stay there.
- **HTTP:** [`curl_cffi`](https://github.com/lexiforest/curl_cffi) (browser-impersonating) —
  primary; `httpx`/`requests` acceptable for prototyping.
- **Fallback browser:** `playwright` (Chromium, headless).
- **Data:** `pandas` → CSV/Parquet; optionally SQLite for daily-delta history.
- **Config/CLI:** `pydantic-settings` or `argparse`; `.env` for cookies.
- **Resilience:** `tenacity` (retries/backoff), `python-dotenv`.
- **Env manager:** `uv` or `venv` + `requirements.txt` (avoid Conda unless preferred).

```
tokped-scraper/
├── RESEARCH_PLAN.md          # this file
├── requirements.txt
├── .env                      # TOKPED_COOKIE=... (gitignored)
├── config/
│   └── city_ids.json         # location filter lookup
├── src/
│   ├── client.py             # GraphQL request wrapper (headers, cookies, retry)
│   ├── search.py             # SearchProductQueryV4 → product list
│   ├── product_detail.py     # PDPGetLayoutQuery → exact countSold (optional)
│   ├── parse.py              # JSON → normalized row dict
│   ├── models.py             # dataclass/pydantic Product schema
│   └── runner.py             # keyword × city loop, pagination, dedupe
├── data/
│   └── raw/  processed/      # dated CSV outputs
└── notebooks/
    └── analysis.ipynb        # official vs non-official comparison + charts
```

---

## 9. Implementation phases

**Phase 0 — Recon (manual, ~1 hr)**
- Open tokopedia.com, search a target keyword, apply **location** + **official store**
  filters. In DevTools → Network → `graphql`, capture: exact operation name, full request
  payload (variables), headers, and cookie. Confirm the current `SearchProductQuery*`
  version and the `fcity` value for our cities.

**Phase 1 — Single-request PoC**
- Reproduce one captured request in Python (`curl_cffi`). Confirm 200 + parse
  `ace_search_product_v4.data.products`. Extract the target fields for one page.

**Phase 2 — Pagination + normalization**
- Loop `start`/`page` until N results or empty. Normalize each product → row schema (§1).
  Parse sold label from `labelGroups`. Write CSV.

**Phase 3 — Location & official filters**
- Wire `fcity` from `city_ids.json` and `official=true/false`. Run keyword × city matrix.
  Produce two sets: official vs non-official.

**Phase 4 — Exact sold (optional) + daily deltas**
- For shortlisted products, call `PDPGetLayoutQuery` for `txStats.countSold`.
- Add SQLite history + daily-delta job (cron / Task Scheduler) for true sell-through velocity.

**Phase 5 — Analysis**
- Notebook: for each keyword, compare official vs non-official on median price, sold count,
  rating, and top-N ranking share. Chart the sold-count gap.

**Phase 6 — Hardening**
- Add retries/backoff, rate-limit jitter, cookie-refresh routine, and the Playwright fallback
  (approach C) for when the direct API returns 403.

---

## 10. Risks & open questions

- **API drift:** operation name/params (`V4`→`V5`) and hashed fields change without notice →
  Phase 0 recon must be repeatable; keep the captured payload in the repo.
- **Bot blocks:** may force the Playwright fallback (approach C). Paid APIs are out of scope.
- **Sold-count granularity:** search gives buckets (`100+`); exact needs PDP calls or daily deltas.
- **Cookie lifetime:** session cookies expire — need a refresh mechanism (manual paste vs. a
  short Playwright "warm-up" that harvests a fresh cookie).
- **City-ID table:** must be built manually via the UI filter (no public list).
- **Legal/ToS:** scraping may violate Tokopedia's Terms of Service. Use only for internal
  competitive analysis, keep volumes low/respectful, don't republish personal data, and
  confirm this is acceptable for our purposes before scaling.

**Decisions — resolved:**
1. ✅ Keywords: `iqos`, `iluma`, `terea`. Cities: `jabodetabek`, `bandung`, `medan`, `surabaya`.
2. ✅ Need **exact** sold numbers → pull from product detail (`PDPGetLayoutQuery →
   txStats.countSold`), stored as `sold_count_exact` alongside the bucketed `sold_count`.
3. ✅ **Self-hosted only** — no paid API. Playwright is the sole fallback if blocked.

---

## 11. Sources

- [hannah2gah/web-scraping-tokopedia](https://github.com/hannah2gah/web-scraping-tokopedia)
- [crypter70/Tokopedia-Scraper](https://github.com/crypter70/Tokopedia-Scraper)
- [SuspiciousLookingOwl/tokopedia-gql (param reference)](https://github.com/SuspiciousLookingOwl/tokopedia-gql)
- [Automated Daily Sales Tracker — Scraping Tokopedia with Python (Medium)](https://rafisunggoro.medium.com/automated-daily-sales-tracker-scraping-tokopedia-with-python-893bcac294a9)
- [Scrapping Data Tokopedia berdasarkan Data Pencarian (Medium)](https://medium.com/@ooemam/scrapping-data-tokopedia-python-berdasarkan-datapencarian-9c22e36aec8c)
- [Tokopedia Product Search Scraper (Apify)](https://apify.com/ecomscrape/tokopedia-product-search-scraper)
- [How to Bypass Cloudflare When Web Scraping in 2026 (Scrapfly)](https://scrapfly.io/blog/posts/how-to-bypass-cloudflare-anti-scraping)
</content>
</invoke>
