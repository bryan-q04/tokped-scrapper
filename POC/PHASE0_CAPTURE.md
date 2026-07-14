# Phase 0 — Tokopedia API capture checklist

Goal: capture the **real** requests/responses so I can align `query.py`, `search.py`,
`product_detail.py`, and `config/city_ids.json` to the live API (fixing the "0 products").

## Status (updated 2026-07)
- ✅ **#1 Search** — captured. Code updated to `SearchProductV5Query` (root `searchProductV5`).
- ✅ **#3/#4 City IDs** — from the `FilterSortProductQuery` filter response, now in `city_ids.json`:
  Jabodetabek `144,146,150,151,167,168,171,174,175,176,177,178,179,463`, Bandung `165`,
  Medan `46`, Surabaya `252`.
- ✅ **#5 Official filter** — it's `shop_tier=2` (Mall/Official Store); `shop.tier==2` in product data.
- ✅ **#6 Sort** — `ob`: 23=best match (default), 5=reviews, 9=newest, 4=price high, 3=price low.
- ⬜ **#2 Product detail (exact sold)** — STILL NEEDED. This is the only remaining capture.

## How to capture (do this once, then repeat per row)

1. Open <https://www.tokopedia.com> in Chrome, press **F12** → **Network** tab.
2. In the Network filter box, type **`graphql`** (or `gql`).
3. Do the **Action** in the row below.
4. Click the matching request, then:
   - **Request** → right-click → **Copy → Copy as cURL (bash)**
   - **Response** → open the **Response** tab → select all → copy (or right-click → Copy → **Copy response**)
5. Paste both into our chat (or save as files). **You may redact the `cookie:` value** — I only
   need to see *which* headers exist, not the secret. I do need the payload + response in full.

> Tip: to find which request holds the sold count, use the Network panel search (the 🔍 icon)
> and type **`countSold`** — it highlights the response that contains it.

## Capture list (priority order)

| # | Priority | Action in browser | Copy | What I extract |
|---|----------|-------------------|------|----------------|
| 1 | 🔴 must  | Search **`iqos`** (no filters) | cURL **+ response** of the `SearchProductQuery*` request | Exact **operation name** (V4/V5/other), endpoint URL, the `variables`/`params` format, required `x-*` headers, and the **response shape** (where `products[]` and the sold field live) |
| 2 | 🔴 must  | On the `iqos` results, open **Product detail** of any item | cURL **+ response** of the request whose response contains `countSold`/`txStats` (search `countSold`) | Exact **PDP operation name**, its `variables` (shopDomain/productKey or productID), and the JSON path to the **exact sold** number |
| 3 | 🟠 high  | On `iqos` results, apply **Location filter** → tick **Jakarta Pusat** (then Bogor/Depok/Tangerang/Bekasi for Jabodetabek) | The **address-bar URL** (easiest) or the request cURL | The `fcity` **param name** + the numeric **city IDs** → fills `config/city_ids.json` |
| 4 | 🟠 high  | Repeat #3 ticking **Bandung**, then **Medan**, then **Surabaya** (one at a time) | address-bar URL each time | city IDs for the other 3 cities |
| 5 | 🟡 nice  | On `iqos` results, toggle the **Official Store** filter on | address-bar URL or request cURL | Exact **official-store filter** param (name + value, e.g. `official=true`?) |
| 6 | 🟡 nice  | Change **Urutkan** (sort) to each option, esp. anything like "Terlaris"/most-sold | address-bar URL each time | The `ob` **sort codes** (so we can sort by most-sold) |

## Fastest path (if you only do two things)
- **#1** (basic search cURL + response) → unblocks live scraping.
- **#2** (product-detail cURL + response) → unblocks exact sold count.

Rows #3–#6 I can partly infer, but the exact **city IDs** (#3/#4) must come from you — there's
no public list. For those, the browser **address bar already shows `fcity=...`** after you apply
the filter, so you can just copy the URL — no DevTools needed.

## What I do with each capture
- #1 → rewrite `src/query.py` (`SEARCH_QUERY`) + `src/search.py` (`build_params`, `extract_products`) to match.
- #2 → rewrite `src/product_detail.py` (`PDP_QUERY`, `build_pdp_payload`, count-sold path) + `client.post_pdp`.
- #3/#4 → fill `config/city_ids.json` with real IDs and set `"verified": true`.
- #5 → set the correct official-filter param in `search.build_params`.
- #6 → document/enable `--sort` codes.
</content>
