from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from .config import AppConfig, ShopConfig
from .discovery import discover_categories
from .fetcher import FetchError, Fetcher
from .parser import find_next_page, parse_listing
from .storage import Storage, utc_now_iso

log = logging.getLogger(__name__)


@dataclass
class ShopResult:
    shop_id: str
    categories_visited: int
    pages_fetched: int
    products_stored: int
    errors: list[str]


def _page_url(category_url: str, mode: str, param: str | None, template: str | None, page: int) -> str:
    if page == 1:
        return category_url
    if mode == "query" and param:
        parsed = urlparse(category_url)
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        qs[param] = str(page)
        return urlunparse(parsed._replace(query=urlencode(qs)))
    if mode == "path" and template:
        joiner = "" if category_url.endswith("/") else "/"
        return category_url + joiner + template.format(n=page).lstrip("/")
    return category_url


def scrape_shop(shop: ShopConfig, storage: Storage, scraped_at: str) -> ShopResult:
    result = ShopResult(shop.id, 0, 0, 0, [])
    if not shop.enabled:
        log.info("shop %s disabled, skipping", shop.id)
        return result

    fetcher = Fetcher(shop.request)

    try:
        categories = discover_categories(shop, fetcher)
    except (FetchError, ValueError) as exc:
        msg = f"discovery failed: {exc}"
        log.error("[%s] %s", shop.id, msg)
        result.errors.append(msg)
        return result

    if not categories:
        log.warning("[%s] no category URLs configured", shop.id)
        return result

    pag = shop.listing.pagination

    for category_url in categories:
        result.categories_visited += 1
        page = 1
        next_url: str | None = category_url
        visited: set[str] = set()
        while next_url and page <= pag.max_pages:
            url = next_url if pag.mode == "next_link" else _page_url(
                category_url, pag.mode, pag.param, pag.template, page
            )
            if url in visited:
                # Pagination linked back to a page we've already fetched —
                # treat as end-of-list to avoid infinite loops on buggy sites.
                log.info("[%s] %s: hit already-visited URL %s, stopping",
                         shop.id, category_url, url)
                break
            visited.add(url)

            try:
                html = fetcher.get(url)
            except FetchError as exc:
                msg = f"fetch {url}: {exc}"
                log.warning("[%s] %s", shop.id, msg)
                result.errors.append(msg)
                break

            result.pages_fetched += 1
            products = parse_listing(html, shop.base_url, shop.listing)
            stored = storage.insert_prices(
                shop.id, category_url, products, scraped_at=scraped_at
            )
            result.products_stored += stored

            log.info(
                "[%s] %s page %d: %d products",
                shop.id, category_url, page, len(products),
            )

            # Stop if a page yielded nothing — likely past the last page.
            if not products:
                break

            if pag.mode == "next_link":
                next_url = find_next_page(html, shop.base_url, pag.next_selector)
                if not next_url:
                    break
            elif pag.mode in ("query", "path"):
                next_url = category_url  # any non-None to continue the loop
            else:
                break

            page += 1

    return result


def run_all(cfg: AppConfig, storage: Storage) -> list[ShopResult]:
    ts = utc_now_iso()
    results: list[ShopResult] = []
    for shop in cfg.shops:
        log.info("=== %s (%s) ===", shop.id, shop.name)
        results.append(scrape_shop(shop, storage, scraped_at=ts))
    return results
