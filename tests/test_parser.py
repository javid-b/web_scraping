from pathlib import Path

from price_scraper.config import ListingConfig, PaginationConfig
from price_scraper.parser import find_next_page, parse_listing, parse_price


FIXTURE = Path(__file__).parent / "fixtures" / "sample_listing.html"


def _listing() -> ListingConfig:
    return ListingConfig(
        product_selector=".product-card",
        name_selector=".product-title",
        price_selector=".price",
        link_selector="a",
        pagination=PaginationConfig(mode="next_link", next_selector=".next-page"),
    )


def test_parse_price_azn_comma_decimal():
    v, c = parse_price("2 499,00 ₼")
    assert v == 2499.00
    assert c == "AZN"


def test_parse_price_azn_dot_decimal():
    v, c = parse_price("2199.50 AZN")
    assert v == 2199.50
    assert c == "AZN"


def test_parse_price_thousands_no_decimal():
    v, c = parse_price("1,299 AZN")
    assert v == 1299.0
    assert c == "AZN"


def test_parse_price_mixed_separators():
    v, _ = parse_price("1.299,90 ₼")
    assert v == 1299.90


def test_parse_price_empty():
    v, c = parse_price("")
    assert v is None and c is None


def test_parse_listing_extracts_products_and_dedupes():
    html = FIXTURE.read_text(encoding="utf-8")
    products = parse_listing(html, "https://example.az", _listing())
    names = [p.name for p in products]
    assert "Apple iPhone 15 128GB Black" in names
    assert "Samsung Galaxy S24 256GB" in names
    assert "Mystery Item" in names
    # Duplicate iPhone entry should be folded into one row.
    assert names.count("Apple iPhone 15 128GB Black") == 1

    by_name = {p.name: p for p in products}
    assert by_name["Apple iPhone 15 128GB Black"].price_value == 2499.0
    assert by_name["Samsung Galaxy S24 256GB"].price_value == 2199.5
    assert by_name["Mystery Item"].price_value is None
    assert by_name["Apple iPhone 15 128GB Black"].product_url == "https://example.az/product/iphone-15-128gb"


def test_find_next_page_resolves_relative_link():
    html = FIXTURE.read_text(encoding="utf-8")
    url = find_next_page(html, "https://example.az", ".next-page")
    assert url == "https://example.az/category/test?page=2"


def test_find_next_page_returns_none_when_missing():
    assert find_next_page("<html></html>", "https://example.az", ".next-page") is None
    assert find_next_page("<html></html>", "https://example.az", None) is None
