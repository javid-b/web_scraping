from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RequestConfig:
    user_agent: str = "Mozilla/5.0"
    delay_seconds: float = 1.0
    timeout: int = 20
    max_retries: int = 3
    engine: str = "requests"   # "requests" or "cloudscraper"


@dataclass
class PaginationConfig:
    mode: str = "none"             # none | query | path | next_link
    param: str | None = None
    template: str | None = None
    next_selector: str | None = None
    max_pages: int = 1000          # safety cap; the scraper stops naturally
                                    # when a page returns 0 products or there
                                    # is no next-link, so this is rarely hit


@dataclass
class ListingConfig:
    product_selector: str = ".product-card"
    name_selector: str | None = None
    price_selector: str = ".price"
    link_selector: str = "a"
    pagination: PaginationConfig = field(default_factory=PaginationConfig)


@dataclass
class DiscoveryConfig:
    mode: str = "static"
    category_urls: list[str] = field(default_factory=list)
    sitemap_url: str | None = None
    menu_selector: str | None = None
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    leaf_only: bool = True   # drop parent-path URLs when a child path is present
    engine: str | None = None  # override request.engine just for the menu/sitemap fetch


@dataclass
class ShopConfig:
    id: str
    name: str
    base_url: str
    enabled: bool = True
    request: RequestConfig = field(default_factory=RequestConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    listing: ListingConfig = field(default_factory=ListingConfig)


@dataclass
class StorageConfig:
    db_path: str = "data/prices.db"


@dataclass
class MergeConfig:
    fuzzy_threshold: int = 88
    min_name_length: int = 4


@dataclass
class AppConfig:
    shops: list[ShopConfig]
    defaults_request: RequestConfig
    storage: StorageConfig
    merge: MergeConfig


def _merge_request(base: dict[str, Any], override: dict[str, Any] | None) -> RequestConfig:
    merged = dict(base or {})
    merged.update(override or {})
    return RequestConfig(
        user_agent=merged.get("user_agent", "Mozilla/5.0"),
        delay_seconds=float(merged.get("delay_seconds", 1.0)),
        timeout=int(merged.get("timeout", 20)),
        max_retries=int(merged.get("max_retries", 3)),
        engine=merged.get("engine", "requests"),
    )


def _pagination(raw: dict[str, Any] | None) -> PaginationConfig:
    raw = raw or {}
    return PaginationConfig(
        mode=raw.get("mode", "none"),
        param=raw.get("param"),
        template=raw.get("template"),
        next_selector=raw.get("next_selector"),
        max_pages=int(raw.get("max_pages", 1000)),
    )


def _listing(raw: dict[str, Any] | None) -> ListingConfig:
    raw = raw or {}
    return ListingConfig(
        product_selector=raw.get("product_selector", ".product-card"),
        name_selector=raw.get("name_selector"),
        price_selector=raw.get("price_selector", ".price"),
        link_selector=raw.get("link_selector", "a"),
        pagination=_pagination(raw.get("pagination")),
    )


def _discovery(raw: dict[str, Any] | None) -> DiscoveryConfig:
    raw = raw or {}
    return DiscoveryConfig(
        mode=raw.get("mode", "static"),
        category_urls=list(raw.get("category_urls") or []),
        sitemap_url=raw.get("sitemap_url"),
        menu_selector=raw.get("menu_selector"),
        include=list(raw.get("include") or []),
        exclude=list(raw.get("exclude") or []),
        leaf_only=bool(raw.get("leaf_only", True)),
        engine=raw.get("engine"),
    )


def load_config(path: str | Path) -> AppConfig:
    """Parse shops.yaml into typed dataclasses."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    defaults = raw.get("defaults") or {}
    default_request = defaults.get("request") or {}

    shops: list[ShopConfig] = []
    for entry in raw.get("shops") or []:
        if "id" not in entry or "base_url" not in entry:
            raise ValueError(f"shop entry missing id/base_url: {entry!r}")
        shops.append(
            ShopConfig(
                id=entry["id"],
                name=entry.get("name", entry["id"]),
                base_url=entry["base_url"].rstrip("/"),
                enabled=bool(entry.get("enabled", True)),
                request=_merge_request(default_request, entry.get("request")),
                discovery=_discovery(entry.get("discovery")),
                listing=_listing(entry.get("listing")),
            )
        )

    storage_raw = defaults.get("storage") or {}
    merge_raw = defaults.get("merge") or {}

    return AppConfig(
        shops=shops,
        defaults_request=_merge_request({}, default_request),
        storage=StorageConfig(db_path=storage_raw.get("db_path", "data/prices.db")),
        merge=MergeConfig(
            fuzzy_threshold=int(merge_raw.get("fuzzy_threshold", 88)),
            min_name_length=int(merge_raw.get("min_name_length", 4)),
        ),
    )
