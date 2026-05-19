from pathlib import Path

from price_scraper.config import load_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_shipped_config():
    cfg = load_config(REPO_ROOT / "config" / "shops.yaml")
    ids = {s.id for s in cfg.shops}
    assert ids == {
        "bakuelectronics", "irshad", "kontakt",
        "mgstore", "elitoptimal", "soliton", "wt",
    }
    for s in cfg.shops:
        assert s.base_url.startswith("https://")
        assert s.listing.product_selector
        assert s.request.timeout > 0
    assert cfg.storage.db_path == "data/prices.db"
    assert cfg.merge.fuzzy_threshold == 88
