from __future__ import annotations

import logging
import re
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, Tag

from .config import DiscoveryConfig, ShopConfig
from .fetcher import Fetcher
from .menu_finder import _filter_to_leaves

log = logging.getLogger(__name__)


def _apply_filters(urls: list[str], include: list[str], exclude: list[str]) -> list[str]:
    inc = [re.compile(p) for p in include] if include else []
    exc = [re.compile(p) for p in exclude] if exclude else []
    out: list[str] = []
    for u in urls:
        if exc and any(p.search(u) for p in exc):
            continue
        if inc and not any(p.search(u) for p in inc):
            continue
        out.append(u)
    # De-dupe preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def _from_sitemap(fetcher: Fetcher, sitemap_url: str) -> list[str]:
    xml = fetcher.get(sitemap_url)
    urls: list[str] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        log.warning("failed to parse sitemap %s: %s", sitemap_url, exc)
        return urls

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in root.findall(".//sm:loc", ns):
        if loc.text:
            urls.append(loc.text.strip())
    # Also handle nested sitemap-index files: recurse one level.
    nested = [u for u in urls if u.endswith(".xml")]
    if nested and len(nested) == len(urls):
        expanded: list[str] = []
        for u in nested:
            try:
                expanded.extend(_from_sitemap(fetcher, u))
            except Exception as exc:  # noqa: BLE001
                log.warning("nested sitemap fetch failed %s: %s", u, exc)
        return expanded
    return urls


def _from_menu(fetcher: Fetcher, base_url: str, selector: str) -> list[str]:
    html = fetcher.get(base_url)
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for el in soup.select(selector):
        if not isinstance(el, Tag):
            continue
        href = el.get("href")
        if href:
            urls.append(urljoin(base_url, href))
    return urls


def discover_categories(shop: ShopConfig, fetcher: Fetcher) -> list[str]:
    """Return category URLs for the shop according to its discovery config."""
    d: DiscoveryConfig = shop.discovery
    if d.mode == "static":
        urls = list(d.category_urls)
    elif d.mode == "sitemap":
        if not d.sitemap_url:
            raise ValueError(f"{shop.id}: discovery.sitemap_url is required for mode=sitemap")
        urls = _from_sitemap(fetcher, d.sitemap_url)
    elif d.mode == "menu":
        if not d.menu_selector:
            raise ValueError(f"{shop.id}: discovery.menu_selector is required for mode=menu")
        urls = _from_menu(fetcher, shop.base_url, d.menu_selector)
    else:
        raise ValueError(f"{shop.id}: unknown discovery mode {d.mode!r}")

    urls = _apply_filters(urls, d.include, d.exclude)
    if d.leaf_only and d.mode != "static":
        # Menus often list a parent category alongside its children; scraping
        # the parent would re-fetch the children's products. Drop parents.
        # Static mode is left alone because the user wrote the list explicitly.
        urls = _filter_to_leaves(urls)
    return urls
