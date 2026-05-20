from dataclasses import replace

from price_scraper.config import DiscoveryConfig, ListingConfig, RequestConfig, ShopConfig
from price_scraper.discovery import discover_categories


class _StubFetcher:
    """Returns a fixed HTML string instead of doing HTTP."""

    def __init__(self, html: str) -> None:
        self.html = html

    def get(self, url: str) -> str:
        return self.html


def _shop(discovery: DiscoveryConfig) -> ShopConfig:
    return ShopConfig(
        id="t",
        name="Test",
        base_url="https://shop.az",
        enabled=True,
        request=RequestConfig(),
        discovery=discovery,
        listing=ListingConfig(),
    )


def test_menu_discovery_filters_to_leaf_urls():
    """When the menu HTML lists a parent and its children, only the children
    should be returned (parents would re-fetch the same products)."""
    html = """
    <html><body>
      <div class="menu">
        <a class="ml" href="/cat">Cat</a>
        <a class="ml" href="/cat/sub-a">Sub A</a>
        <a class="ml" href="/cat/sub-b">Sub B</a>
        <a class="ml" href="/other">Other</a>
      </div>
    </body></html>
    """
    shop = _shop(DiscoveryConfig(mode="menu", menu_selector="a.ml"))
    urls = discover_categories(shop, _StubFetcher(html))
    assert set(urls) == {
        "https://shop.az/cat/sub-a",
        "https://shop.az/cat/sub-b",
        "https://shop.az/other",
    }


def test_menu_discovery_respects_leaf_only_false():
    """Setting leaf_only: false keeps parent URLs alongside children."""
    html = """
    <html><body>
      <div class="menu">
        <a class="ml" href="/cat">Cat</a>
        <a class="ml" href="/cat/sub-a">Sub A</a>
      </div>
    </body></html>
    """
    shop = _shop(DiscoveryConfig(mode="menu", menu_selector="a.ml", leaf_only=False))
    urls = discover_categories(shop, _StubFetcher(html))
    assert set(urls) == {"https://shop.az/cat", "https://shop.az/cat/sub-a"}


def test_static_discovery_never_filters_leaves():
    """leaf_only is ignored in static mode — the user wrote the list."""
    shop = _shop(DiscoveryConfig(
        mode="static",
        category_urls=["https://shop.az/cat", "https://shop.az/cat/sub-a"],
        leaf_only=True,
    ))
    urls = discover_categories(shop, _StubFetcher(""))
    assert urls == ["https://shop.az/cat", "https://shop.az/cat/sub-a"]


def test_discovery_engine_override_is_parsed():
    """`discovery.engine` in YAML should land on DiscoveryConfig.engine, so the
    runner can spin up a Playwright fetcher just for the menu fetch and reuse
    a cloudscraper fetcher for the bulk listings."""
    import yaml
    from price_scraper.config import load_config
    from pathlib import Path

    cfg_text = """
shops:
  - id: kontakt
    name: Kontakt
    base_url: https://kontakt.az
    request:
      engine: cloudscraper
    discovery:
      mode: menu
      menu_selector: "a.contentMenu__title[href]"
      engine: playwright
    listing:
      product_selector: ".prodItem"
defaults:
  request:
    user_agent: "x"
    engine: requests
"""
    tmp = Path("/tmp/_test_cfg.yaml")
    tmp.write_text(cfg_text)
    cfg = load_config(tmp)
    s = cfg.shops[0]
    assert s.request.engine == "cloudscraper"
    assert s.discovery.engine == "playwright"
