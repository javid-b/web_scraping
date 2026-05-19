from pathlib import Path

from price_scraper.parser import ScrapedProduct
from price_scraper.storage import Storage, utc_now_iso


def _product(name, price, url=None, currency="AZN"):
    return ScrapedProduct(name=name, price_value=price, price_currency=currency, product_url=url)


def test_insert_and_history(tmp_path: Path):
    db = tmp_path / "p.db"
    s = Storage(db)
    try:
        t1 = "2026-05-10T00:00:00Z"
        t2 = "2026-05-11T00:00:00Z"
        s.insert_prices("kontakt", "https://kontakt.az/c1",
                        [_product("iPhone 15", 2499.0, "https://kontakt.az/p/1")], scraped_at=t1)
        s.insert_prices("kontakt", "https://kontakt.az/c1",
                        [_product("iPhone 15", 2399.0, "https://kontakt.az/p/1")], scraped_at=t2)

        rows = s.price_history("kontakt", "iPhone 15")
        assert len(rows) == 2
        assert [r["price_value"] for r in rows] == [2499.0, 2399.0]
        assert [r["scraped_at"] for r in rows] == [t1, t2]
    finally:
        s.close()


def test_distinct_products(tmp_path: Path):
    s = Storage(tmp_path / "p.db")
    try:
        s.insert_prices("a", "u", [_product("X", 1.0), _product("X", 1.0), _product("Y", 2.0)])
        s.insert_prices("b", "u", [_product("X", 1.5)])
        assert set(s.distinct_products()) == {("a", "X"), ("a", "Y"), ("b", "X")}
    finally:
        s.close()


def test_replace_clusters_round_trip(tmp_path: Path):
    s = Storage(tmp_path / "p.db")
    try:
        s.insert_prices("a", "u", [_product("X", 1.0)])
        s.insert_prices("b", "u", [_product("X", 1.5)])
        s.replace_clusters([
            (0, "a", "X", "X"),
            (0, "b", "X", "X"),
        ])
        rows = s.cluster_latest(0)
        shops = {r["shop_id"] for r in rows}
        assert shops == {"a", "b"}
    finally:
        s.close()


def test_utc_now_iso_format():
    ts = utc_now_iso()
    assert ts.endswith("Z")
    assert len(ts) == len("YYYY-MM-DDTHH:MM:SSZ")
