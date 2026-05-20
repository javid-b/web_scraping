"""Tests for the politeness / stealth-adjacent features:

* Randomised delay jitter (`delay_jitter`).
* Periodic long pauses (`long_pause_every`).
* Shuffled category order at scrape time.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from price_scraper.config import RequestConfig, load_config


def test_request_config_parses_politeness_fields(tmp_path: Path):
    cfg_text = """
shops:
  - id: a
    name: A
    base_url: https://a.az
    request:
      delay_seconds: 3
      delay_jitter: 4
      long_pause_every: 40
      long_pause_seconds: 30
      long_pause_jitter: 60
    listing: {product_selector: ".p"}
"""
    p = tmp_path / "c.yaml"
    p.write_text(cfg_text)
    cfg = load_config(p)
    r = cfg.shops[0].request
    assert r.delay_seconds == 3.0
    assert r.delay_jitter == 4.0
    assert r.long_pause_every == 40
    assert r.long_pause_seconds == 30.0
    assert r.long_pause_jitter == 60.0


def test_request_config_defaults_are_polite():
    """Empty config should still give a slow-but-working RequestConfig."""
    r = RequestConfig()
    assert r.delay_seconds >= 0
    assert r.long_pause_every == 0   # disabled by default at the dataclass level
    assert r.delay_jitter == 0.0


def test_runner_shuffles_categories(monkeypatch, tmp_path: Path):
    """The runner should permute the category list so the daily access
    pattern doesn't always start with the same URL."""
    seen_order: list[list[str]] = []

    captured = {"called": 0}

    class StubFetcher:
        def __init__(self, cfg):
            captured["called"] += 1

        def get(self, url):
            # First page yields one product, then empty so the loop exits.
            return "<html><body></body></html>"

        def close(self):
            pass

    monkeypatch.setattr("price_scraper.runner.Fetcher", StubFetcher)
    monkeypatch.setattr(
        "price_scraper.runner.discover_categories",
        lambda shop, fetcher: [f"https://x.az/c{i}" for i in range(12)],
    )

    def capturing_shuffle(seq):
        seen_order.append(list(seq))
        # Force a non-identity permutation so we can detect that shuffle ran.
        seq.reverse()

    monkeypatch.setattr("price_scraper.runner.random.shuffle", capturing_shuffle)

    from price_scraper.config import (
        DiscoveryConfig, ListingConfig, PaginationConfig, ShopConfig, StorageConfig,
    )
    from price_scraper.runner import scrape_shop
    from price_scraper.storage import Storage

    shop = ShopConfig(
        id="t", name="T", base_url="https://x.az", enabled=True,
        request=RequestConfig(),
        discovery=DiscoveryConfig(mode="static", category_urls=[]),
        listing=ListingConfig(pagination=PaginationConfig(mode="none")),
    )
    storage = Storage(tmp_path / "p.db")
    try:
        scrape_shop(shop, storage, scraped_at="2026-05-20T00:00:00Z")
    finally:
        storage.close()
    assert seen_order, "random.shuffle was never called — categories not shuffled"
    assert seen_order[0] == [f"https://x.az/c{i}" for i in range(12)]


def test_fetcher_sleep_respects_jitter(monkeypatch):
    """The actual delay between requests should fall in
    [delay_seconds, delay_seconds + delay_jitter]."""
    from price_scraper.fetcher import Fetcher

    sleeps: list[float] = []
    monkeypatch.setattr("price_scraper.fetcher.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("price_scraper.fetcher.time.monotonic", lambda: 0.0)
    # Force jitter samples to a known value so the assertion is deterministic.
    monkeypatch.setattr("price_scraper.fetcher.random.uniform", lambda lo, hi: hi)

    f = Fetcher(RequestConfig(delay_seconds=2.0, delay_jitter=3.0, engine="requests"))
    f._sleep_if_needed()
    assert sleeps == [pytest.approx(5.0)]   # 2 base + 3 max jitter


def test_fetcher_long_pause_fires_every_n_requests(monkeypatch):
    from price_scraper.fetcher import Fetcher

    sleeps: list[float] = []
    monkeypatch.setattr("price_scraper.fetcher.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("price_scraper.fetcher.time.monotonic", lambda: 0.0)
    monkeypatch.setattr("price_scraper.fetcher.random.uniform", lambda lo, hi: 0.0)

    f = Fetcher(RequestConfig(
        delay_seconds=1.0, delay_jitter=0.0,
        long_pause_every=3, long_pause_seconds=30.0, long_pause_jitter=0.0,
        engine="requests",
    ))
    for _ in range(7):
        f._sleep_if_needed()
    # Each call sleeps 1.0 (delay), and every 3rd call also sleeps 30.0.
    short = [s for s in sleeps if s < 10]
    long = [s for s in sleeps if s >= 10]
    assert len(short) == 7
    assert len(long) == 2  # after requests 3 and 6
