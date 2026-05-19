from pathlib import Path

from price_scraper.suggester import detect_pagination, render_suggestions, suggest


FIXTURES = Path(__file__).parent / "fixtures"


def test_suggest_picks_catalog_item_layout():
    html = (FIXTURES / "realistic_listing.html").read_text(encoding="utf-8")
    suggestions = suggest(html, max_results=3)

    assert suggestions, "expected at least one suggestion"
    top = suggestions[0]
    assert top.product_selector == ".catalog-item"
    assert top.price_selector == ".catalog-item__price"
    # Any of these is equivalent: the <a class="catalog-item__link"> wraps the
    # <h3 class="catalog-item__title">, so all three yield the same text.
    assert top.name_selector in (".catalog-item__title", ".catalog-item__link", "h3")
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


def test_detect_pagination_rel_next():
    html = '<html><body><a rel="next" href="/p/2">Next</a></body></html>'
    p = detect_pagination(html)
    assert p is not None and p.mode == "next_link"
    assert p.next_selector == 'a[rel="next"]'


def test_detect_pagination_query_param():
    html = """
    <html><body>
      <div class="pg">
        <a href="?page=1">1</a>
        <a href="?page=2">2</a>
        <a href="?page=3">3</a>
      </div>
    </body></html>
    """
    p = detect_pagination(html)
    assert p is not None and p.mode == "query"
    assert p.param == "page"


def test_detect_pagination_path():
    html = """
    <html><body>
      <a href="/category/laptops/page/2/">2</a>
      <a href="/category/laptops/page/3/">3</a>
    </body></html>
    """
    p = detect_pagination(html)
    assert p is not None and p.mode == "path"
    assert p.template == "/page/{n}"


def test_detect_pagination_load_more_button():
    html = """
    <html><body>
      <button class="load-more-btn" data-href="/products?page=2">
        Daha çox göstər
      </button>
    </body></html>
    """
    p = detect_pagination(html)
    assert p is not None and p.mode == "next_link"
    assert p.next_selector == ".load-more-btn"
    assert "daha" in p.note.lower() or "load" in p.note.lower()


def test_detect_pagination_load_more_button_without_href_warns():
    html = """
    <html><body>
      <button class="js-only-btn">Daha çox göstər</button>
    </body></html>
    """
    p = detect_pagination(html)
    assert p is not None
    assert "playwright" in p.note.lower()


def test_detect_pagination_returns_none_when_absent():
    assert detect_pagination("<html><body>nothing</body></html>") is None


def test_find_next_page_reads_data_href():
    from price_scraper.parser import find_next_page

    html = '<html><body><button class="lm" data-href="/?page=2">More</button></body></html>'
    url = find_next_page(html, "https://example.az", ".lm")
    assert url == "https://example.az/?page=2"
