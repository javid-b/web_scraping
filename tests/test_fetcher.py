from price_scraper.fetcher import Fetcher


def test_fetcher_class_exposes_get_method():
    """Regression test: a copy-paste mishap previously nested `def get(...)`
    inside a module-level helper, so Fetcher had no `get` method. tests didn't
    catch it because none of them actually constructed a Fetcher."""
    assert hasattr(Fetcher, "get"), "Fetcher.get is missing from the class"
    assert hasattr(Fetcher, "close")
    assert callable(Fetcher.get)


def test_fetcher_class_exposes_playwright_helpers():
    assert hasattr(Fetcher, "_get_playwright")
    assert hasattr(Fetcher, "_ensure_playwright")
