# price_scraper

Daily product-price scraper for a library of online shops. Stores every
observation with a timestamp in SQLite, and merges items across shops with
fuzzy name matching so you can compare prices and build historical trends.

Configured for these Azerbaijani electronics retailers (selectors must be
tuned per site — see [Configuring a shop](#configuring-a-shop)):

- bakuelectronics.az
- irshad.az
- kontakt.az
- mgstore.az
- elitoptimal.az
- soliton.az
- w-t.az

## Architecture

```
   shops.yaml
       │
       ▼
   ┌─────────────┐    fetch (requests + retries)    ┌──────────────┐
   │  runner     │ ───────────────────────────────► │  HTML pages  │
   │             │ ◄─────────────────────────────── │              │
   └─────────────┘                                  └──────────────┘
       │ parse (BeautifulSoup)
       ▼
   ┌─────────────┐                                  ┌──────────────┐
   │  storage    │ ───── insert prices ──────────►  │  SQLite DB   │
   │             │                                  │  prices,     │
   │             │ ◄──── distinct names ─────────── │  clusters    │
   └─────────────┘                                  └──────────────┘
       ▲
       │ fuzzy match (rapidfuzz)
   ┌─────────────┐
   │  merger     │
   └─────────────┘
```

Two CLIs:

- `price_scraper scrape` — runs every shop in `shops.yaml` and appends a fresh
  row per product per run (so history is automatic).
- `price_scraper merge` — clusters products across shops by fuzzy-matched
  normalized name, writes the assignment into `product_clusters`, then any
  cluster joins shop-specific prices for cross-shop comparison.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # add [dev] if you want pytest too
```

## Daily workflow

```bash
# 1. Scrape every enabled shop and append today's prices.
price_scraper scrape

# 2. Re-cluster products so newly-scraped items get cross-shop links.
price_scraper merge

# 3. Inspect history of a specific product in a specific shop.
price_scraper history kontakt "Apple iPhone 15 128GB Black"
```

Schedule step 1 (and optionally step 2) with cron, e.g.:

```cron
30 6 * * *  cd /path/to/repo && /path/to/.venv/bin/price_scraper scrape && /path/to/.venv/bin/price_scraper merge
```

## Configuring a shop

The default `config/shops.yaml` ships with **empty `category_urls` lists**
because each retailer has its own URL layout. To wire up a shop:

1. Open the site in your browser and copy a few category-page URLs.
2. Paste them under that shop's `discovery.category_urls`.
3. **Auto-detect selectors** for a category page:

```bash
price_scraper suggest --shop kontakt 'https://kontakt.az/<some-category>'
```

This fetches the page, finds the repeating product-card pattern (sibling
elements sharing a class that contain a price), and prints a ready-to-paste
YAML block, e.g.:

```
=== Layout 1 — 24 cards, 24 with valid price ===
  listing:
    product_selector: ".catalog-item"
    name_selector:    ".catalog-item__title"
    price_selector:   ".catalog-item__price"

  Sample extraction:
       2 899,00 ₼   Apple MacBook Air M2 13" 256GB
       1 499,00 ₼   HP Pavilion 15-eg2034ci i5/16GB/512GB
       ...
```

Paste the three selector lines into the shop's `listing:` block. If the
top suggestion looks wrong, try Layout 2/3 (raise `--limit`).

4. Dry-run the chosen selectors:

```bash
price_scraper inspect kontakt 'https://kontakt.az/<some-category>'
```

Adjust until the price and name come out clean.

### Pagination modes

```yaml
pagination:
  mode: query        # …?page=2, …?page=3
  param: page
  max_pages: 30

pagination:
  mode: path         # …/page/2/
  template: "/page/{n}"

pagination:
  mode: next_link    # follow rel="next" or a CSS-selected anchor
  next_selector: "a.next-page"
```

### Discovery modes

```yaml
discovery:
  mode: static
  category_urls:
    - https://kontakt.az/noutbuklar
    - https://kontakt.az/telefonlar

# or
discovery:
  mode: sitemap
  sitemap_url: https://kontakt.az/sitemap.xml
  include: ["/category/"]
  exclude: ["/blog/", "/news/"]

# or
discovery:
  mode: menu
  menu_selector: "nav.main-menu a"
  include: ["/category/"]
```

## Querying the data

The SQLite file lives at `data/prices.db` by default. Useful queries:

```sql
-- Trend of one product in one shop.
SELECT scraped_at, price_value
FROM prices
WHERE shop_id = 'kontakt' AND product_name = 'Apple iPhone 15 128GB Black'
ORDER BY scraped_at;

-- All shops selling the cluster of one product, latest price each.
SELECT * FROM latest_prices
WHERE cluster_id = (
    SELECT cluster_id FROM product_clusters
    WHERE shop_id='kontakt' AND product_name='Apple iPhone 15 128GB Black'
);

-- Cheapest shop per cluster today.
SELECT canonical_name, shop_id, MIN(price_value) AS price
FROM latest_prices
WHERE cluster_id IS NOT NULL
GROUP BY cluster_id;
```

## Testing

```bash
pytest -q
```

Tests use a fixture HTML page (no network) to verify:

- Price parsing with AZN/USD currency tokens and AZ number formats.
- Listing extraction + deduplication + relative-URL resolution.
- SQLite schema, multi-day history, cluster persistence.
- Fuzzy clustering at different thresholds.
- Loading the shipped `shops.yaml`.

## Notes & limits

- Some shops may return 403 to non-browser User-Agents or block by region.
  `request.user_agent` and `request.delay_seconds` in `shops.yaml` let you
  tune politeness. If a site is fully JS-rendered (no products in initial
  HTML), this scraper won't see them — for those, you'd need to swap in
  Playwright in `fetcher.py`. The current parsing/storage/merge layers stay
  the same.
- Respect each site's robots.txt and terms of service before scraping.
- The cluster step is greedy single-link with `token_set_ratio`; tune
  `defaults.merge.fuzzy_threshold` if you see over- or under-merging.
