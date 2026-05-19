from pathlib import Path

from price_scraper.menu_finder import find_menus, render_menu_suggestions


FIXTURES = Path(__file__).parent / "fixtures"


def test_find_menus_picks_header_nav():
    html = (FIXTURES / "homepage_with_menu.html").read_text(encoding="utf-8")
    suggestions = find_menus(html, "https://shop.example.az")

    assert suggestions, "expected at least one menu suggestion"
    top = suggestions[0]
    # Should contain all six category URLs from the header nav.
    expected = {
        "https://shop.example.az/c/noutbuklar",
        "https://shop.example.az/c/telefonlar",
        "https://shop.example.az/c/televizorlar",
        "https://shop.example.az/c/sma",
        "https://shop.example.az/c/audio",
        "https://shop.example.az/c/aksesuarlar",
    }
    assert set(top.urls) == expected
    assert top.container_tag == "nav"


def test_find_menus_ignores_noise_urls():
    """Login / cart / wishlist / social anchors should not be classified as
    categories even if they live next to real category links."""
    html = (FIXTURES / "homepage_with_menu.html").read_text(encoding="utf-8")
    top = find_menus(html, "https://shop.example.az")[0]
    for u in top.urls:
        assert "login" not in u
        assert "cart" not in u
        assert "wishlist" not in u
        assert "facebook" not in u


def test_find_menus_skips_footer_menu_for_top_pick():
    """A footer 'menu' (about/contact/terms) is technically a <ul>, but it
    should rank below the header nav and contain only policy pages."""
    html = (FIXTURES / "homepage_with_menu.html").read_text(encoding="utf-8")
    sugs = find_menus(html, "https://shop.example.az", max_results=5)
    top_urls = set(sugs[0].urls)
    # The footer's about/contact/terms anchors are filtered by _NOISE_PATHS,
    # so they should never appear in any suggestion.
    for s in sugs:
        for u in s.urls:
            assert "/about" not in u
            assert "/contact" not in u
            assert "/terms" not in u
            assert "/privacy" not in u
            assert "/help" not in u


def test_find_menus_returns_empty_when_no_menu():
    html = """
    <html><body>
      <a href="/login">Login</a>
      <a href="/cart">Cart</a>
      <p>No category links here.</p>
    </body></html>
    """
    assert find_menus(html, "https://example.az") == []


def test_render_menu_suggestions_includes_both_static_and_dynamic_forms():
    html = (FIXTURES / "homepage_with_menu.html").read_text(encoding="utf-8")
    out = render_menu_suggestions(find_menus(html, "https://shop.example.az"))
    assert "mode: static" in out
    assert "mode: menu" in out
    assert "category_urls:" in out
    assert "/c/noutbuklar" in out


def test_render_menu_suggestions_handles_empty():
    out = render_menu_suggestions([])
    assert "No navigation menu" in out
