"""Selector-tuning helper. Fetches a URL and shows what the configured
listing selectors would extract — used to tune CSS selectors against a real
page without running a full scrape."""

from __future__ import annotations

from .config import ShopConfig
from .fetcher import Fetcher
from .parser import parse_listing


def inspect(shop: ShopConfig, url: str, limit: int = 10) -> None:
    fetcher = Fetcher(shop.request)
    html = fetcher.get(url)
    products = parse_listing(html, shop.base_url, shop.listing)
    print(f"shop:      {shop.id} ({shop.name})")
    print(f"url:       {url}")
    print(f"selectors: {shop.listing.product_selector}  |  "
          f"name={shop.listing.name_selector}  price={shop.listing.price_selector}")
    print(f"found:     {len(products)} products")
    print("-" * 60)
    for p in products[:limit]:
        price = f"{p.price_value} {p.price_currency or ''}".strip() if p.price_value else "?"
        print(f"  {price:>14}   {p.name[:80]}")
        if p.product_url:
            print(f"  {'':>14}   {p.product_url}")
