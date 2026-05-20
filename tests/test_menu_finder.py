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


def test_find_menus_kontakt_style_megamenu():
    """Mega menus that put each subcategory in its own `.contentMenu__item`
    wrapper (per-anchor parent) used to break grouping. Group should still
    pick up all subcategory links because they share an outer `.contentMenu`
    ancestor."""
    html = (FIXTURES / "megamenu_kontakt_style.html").read_text(encoding="utf-8")
    suggestions = find_menus(html, "https://example.az")

    assert suggestions, "expected at least one suggestion"
    # The 5 subcategory anchors should all appear together in some suggestion.
    expected = {
        "https://example.az/telefoniya/smartfonlar",
        "https://example.az/telefoniya/klassik",
        "https://example.az/telefoniya/aksesuar",
        "https://example.az/telefoniya/smart-saat",
        "https://example.az/telefoniya/quluqcuq",
    }
    sub_sugs = [s for s in suggestions if expected <= set(s.urls)]
    assert sub_sugs, (
        "no candidate contains all 5 subcategory links; suggestions were: "
        f"{[s.urls for s in suggestions]}"
    )


def test_find_menus_prefers_shared_anchor_class_selector():
    """When every anchor in the menu shares a class (kontakt:
    contentMenu__title), the suggested selector should target the anchors
    directly rather than the container."""
    html = (FIXTURES / "megamenu_kontakt_style.html").read_text(encoding="utf-8")
    suggestions = find_menus(html, "https://example.az")
    sub_sugs = [s for s in suggestions if any("smartfonlar" in u for u in s.urls)]
    assert sub_sugs
    # At least one should use the precise anchor-class selector.
    assert any(s.selector == "a.contentMenu__title[href]" for s in sub_sugs), (
        f"no suggestion used a.contentMenu__title[href]; got "
        f"{[s.selector for s in sub_sugs]}"
    )


def test_find_menus_prefers_shared_anchor_class_over_broad_ul():
    """Kontakt's rendered page contains both a precise menu (~80 links sharing
    a class) and a catch-all <ul> wrapping the whole page (hundreds of
    unrelated links). The precise one must rank first even though the broad
    one has more URLs."""
    precise = "\n".join(
        f'<div class="contentMenu__item"><a class="contentMenu__title" '
        f'href="https://shop.az/c/cat{i}">Category {i}</a></div>'
        for i in range(6)
    )
    noisy = "\n".join(
        f'<li><a href="https://shop.az/random/{i}">Random {i}</a></li>'
        for i in range(50)
    )
    html = f"""
    <html><body>
      <ul>
        <li><div class="contentMenu">{precise}</div></li>
        {noisy}
      </ul>
    </body></html>
    """
    suggestions = find_menus(html, "https://shop.az")
    assert suggestions
    top = suggestions[0]
    assert top.selector == "a.contentMenu__title[href]"
    assert len(top.urls) == 6


def test_find_menus_drops_noisy_superset_of_accepted_candidate():
    """A broader candidate whose URLs are a strict superset of an already-
    accepted candidate should be filtered out as a noisier duplicate."""
    html = """
    <html><body>
      <ul>
        <li><div class="contentMenu">
          <div class="contentMenu__item"><a class="contentMenu__title" href="/alpha">Alpha</a></div>
          <div class="contentMenu__item"><a class="contentMenu__title" href="/beta">Beta</a></div>
          <div class="contentMenu__item"><a class="contentMenu__title" href="/gamma">Gamma</a></div>
          <div class="contentMenu__item"><a class="contentMenu__title" href="/delta">Delta</a></div>
        </div></li>
      </ul>
    </body></html>
    """
    suggestions = find_menus(html, "https://shop.az")
    assert len(suggestions) == 1, (
        f"expected one cohesive suggestion, got {len(suggestions)}: "
        f"{[s.selector for s in suggestions]}"
    )
    assert suggestions[0].selector == "a.contentMenu__title[href]"


def test_filter_to_leaves_drops_parent_paths():
    from price_scraper.menu_finder import _filter_to_leaves

    urls = [
        "https://shop.az/agilli-ev/smart-avadanliqlar",
        "https://shop.az/agilli-ev/smart-avadanliqlar/sensorlar",
        "https://shop.az/agilli-ev/smart-avadanliqlar/isiqlandirma",
        "https://shop.az/telefoniya/smartfonlar",   # no children → kept
        "https://shop.az/telefoniya",
        "https://shop.az/telefoniya/aksesuarlar",
    ]
    leaves = _filter_to_leaves(urls)
    assert "https://shop.az/agilli-ev/smart-avadanliqlar" not in leaves   # has children
    assert "https://shop.az/telefoniya" not in leaves                    # has children
    assert "https://shop.az/agilli-ev/smart-avadanliqlar/sensorlar" in leaves
    assert "https://shop.az/agilli-ev/smart-avadanliqlar/isiqlandirma" in leaves
    assert "https://shop.az/telefoniya/smartfonlar" in leaves
    assert "https://shop.az/telefoniya/aksesuarlar" in leaves


def test_filter_to_leaves_does_not_drop_sibling_with_same_prefix():
    """`/cat/foo` is NOT a parent of `/cat/foobar` — only the slash-separated
    boundary counts."""
    from price_scraper.menu_finder import _filter_to_leaves

    urls = ["https://x.az/cat/foo", "https://x.az/cat/foobar"]
    assert set(_filter_to_leaves(urls)) == set(urls)


def test_find_menus_matches_camelcase_class():
    """`contentMenu` should match the menu-class heuristic even though the
    word 'menu' starts mid-string without a word boundary."""
    html = """
    <html><body>
      <div class="someContentMenu">
        <a href="/alpha">Alpha</a>
        <a href="/beta">Beta</a>
        <a href="/gamma">Gamma</a>
        <a href="/delta">Delta</a>
      </div>
    </body></html>
    """
    suggestions = find_menus(html, "https://example.az")
    assert suggestions
    assert {u for u in suggestions[0].urls} == {
        "https://example.az/alpha", "https://example.az/beta",
        "https://example.az/gamma", "https://example.az/delta",
    }
