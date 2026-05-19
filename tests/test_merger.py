from pathlib import Path

from price_scraper.config import MergeConfig
from price_scraper.merger import merge, normalize
from price_scraper.parser import ScrapedProduct
from price_scraper.storage import Storage


def _p(name, price=1.0):
    return ScrapedProduct(name=name, price_value=price, price_currency="AZN", product_url=None)


def test_normalize_strips_accents_punct_case():
    assert normalize("Şəkər - 1kg!") == "seker 1kg"
    assert normalize("Apple  iPhone  15") == "apple iphone 15"


def test_merge_clusters_similar_names(tmp_path: Path):
    s = Storage(tmp_path / "p.db")
    try:
        s.insert_prices("kontakt", "u", [_p("Apple iPhone 15 128GB Black")])
        s.insert_prices("irshad", "u", [_p("iPhone 15 128 GB - Black (Apple)")])
        s.insert_prices("bakuelectronics", "u", [_p("Samsung Galaxy S24 256GB")])
        s.insert_prices("mgstore", "u", [_p("Samsung S24 256 GB")])

        n = merge(s, MergeConfig(fuzzy_threshold=80, min_name_length=4))
        assert n == 2

        # Each iPhone entry should land in the same cluster.
        iphone_clusters = {
            r["cluster_id"]
            for r in s.conn.execute(
                "SELECT cluster_id FROM product_clusters WHERE product_name LIKE '%iPhone%'"
            )
        }
        assert len(iphone_clusters) == 1

        samsung_clusters = {
            r["cluster_id"]
            for r in s.conn.execute(
                "SELECT cluster_id FROM product_clusters WHERE product_name LIKE '%Samsung%' OR product_name LIKE '%S24%'"
            )
        }
        assert len(samsung_clusters) == 1
        assert iphone_clusters != samsung_clusters
    finally:
        s.close()


def test_merge_respects_high_threshold(tmp_path: Path):
    s = Storage(tmp_path / "p.db")
    try:
        s.insert_prices("a", "u", [_p("Apple iPhone 15 128GB Black")])
        s.insert_prices("b", "u", [_p("Samsung Galaxy S24 256GB")])
        n = merge(s, MergeConfig(fuzzy_threshold=95, min_name_length=4))
        assert n == 2
    finally:
        s.close()
