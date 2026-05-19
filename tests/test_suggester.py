from pathlib import Path

from price_scraper.suggester import render_suggestions, suggest


FIXTURES = Path(__file__).parent / "fixtures"


def test_suggest_picks_catalog_item_layout():
    html = (FIXTURES / "realistic_listing.html").read_text(encoding="utf-8")
    suggestions = suggest(html, max_results=3)

    assert suggestions, "expected at least one suggestion"
    top = suggestions[0]
    assert top.product_selector == ".catalog-item"
    assert top.price_selector == ".catalog-item__price"
    assert top.name_selector in (".catalog-item__title", "h3")
    assert top.product_count == 6
    assert top.price_match_count == 6

    # Sample extraction should include the real product names and prices.
    names = [name for name, _ in top.samples]
    prices = [price for _, price in top.samples]
    assert any("MacBook" in n for n in names)
    assert any("₼" in p for p in prices)


def test_suggest_prefers_current_price_over_old_price():
    """The card has both .catalog-item__price-old and .catalog-item__price.
    We should pick the one matching for all 6 cards, not the one matching just 1.
    """
    html = (FIXTURES / "realistic_listing.html").read_text(encoding="utf-8")
    top = suggest(html, max_results=1)[0]
    assert top.price_selector == ".catalog-item__price"
    # __price-old only appears once and would score 1, not 6.


def test_suggest_returns_empty_for_html_without_products():
    html = "<html><body><p>Just text, no products here.</p></body></html>"
    assert suggest(html) == []


def test_render_suggestions_includes_yaml_keys():
    html = (FIXTURES / "realistic_listing.html").read_text(encoding="utf-8")
    out = render_suggestions(suggest(html, max_results=1))
    assert "product_selector" in out
    assert "price_selector" in out
    assert ".catalog-item" in out


def test_render_empty_suggestions_gives_guidance():
    out = render_suggestions([])
    assert "JavaScript" in out or "no" in out.lower()
