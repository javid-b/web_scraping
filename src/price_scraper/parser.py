from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .config import ListingConfig

# Currency aliases seen on AZ retail sites. Order matters: longer first.
_CURRENCY_TOKENS = [
    ("AZN", "AZN"),
    ("MANAT", "AZN"),
    ("MAN", "AZN"),
    ("₼", "AZN"),       # ₼
    ("USD", "USD"),
    ("$", "USD"),
    ("EUR", "EUR"),
    ("€", "EUR"),       # €
    ("RUB", "RUB"),
    ("₽", "RUB"),       # ₽
]

# Class of chars that can appear inside a number token: ASCII digit, ASCII
# space, NO-BREAK SPACE (U+00A0), NARROW NO-BREAK SPACE (U+202F), comma, dot.
_NUM_CLASS = "[\\d   .,]"
_PRICE_NUMBER_RE = re.compile(r"\d" + _NUM_CLASS + "*")

# Match `<currency> <number>` or `<number> <currency>`. Word currencies use
# word boundaries to avoid matching inside English words.
_CURRENCY_RE = r"(?:\b(?:AZN|MANAT|MAN|USD|EUR|RUB)\b|[₼€₽$])"
_PRICE_WITH_CURRENCY_RE = re.compile(
    rf"(?:{_CURRENCY_RE}\s*(\d{_NUM_CLASS}*)|(\d{_NUM_CLASS}*)\s*{_CURRENCY_RE})",
    re.IGNORECASE,
)


def _normalize_number(raw: str) -> float | None:
    """Parse a number-string like '1 234,56' or '2199.50' into a float."""
    s = raw.strip().replace(" ", " ").replace(" ", " ").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # Both present: the rightmost is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Comma is the decimal separator if it's followed by exactly 1-2 digits.
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _detect_currency(text: str) -> str | None:
    upper = text.upper()
    for token, code in _CURRENCY_TOKENS:
        if token in upper or token in text:
            return code
    return None


def parse_price(text: str) -> tuple[float | None, str | None]:
    """Pull a numeric price + currency out of arbitrary HTML text.

    When the text contains multiple `number + currency` pairs (e.g. a
    crossed-out original price next to a discounted current price), return
    the SMALLEST price — sale prices are lower than originals. Returns
    (None, None) if no number can be parsed.
    """
    if not text:
        return None, None

    currency = _detect_currency(text)

    candidates: list[float] = []
    for m in _PRICE_WITH_CURRENCY_RE.finditer(text):
        raw = m.group(1) or m.group(2) or ""
        v = _normalize_number(raw)
        if v is not None and v > 0:
            candidates.append(v)
    if candidates:
        return min(candidates), currency

    # Fallback when no currency token is present in the text.
    match = _PRICE_NUMBER_RE.search(text)
    if not match:
        return None, currency
    return _normalize_number(match.group(0)), currency


@dataclass
class ScrapedProduct:
    name: str
    price_value: float | None
    price_currency: str | None
    product_url: str | None


def _text(el: Tag | None) -> str:
    return el.get_text(" ", strip=True) if el else ""


def parse_listing(html: str, base_url: str, listing: ListingConfig) -> list[ScrapedProduct]:
    """Extract product cards from a category listing page."""
    soup = BeautifulSoup(html, "lxml")
    products: list[ScrapedProduct] = []
    seen: set[tuple[str, str | None]] = set()

    for card in soup.select(listing.product_selector):
        name_el = card.select_one(listing.name_selector) if listing.name_selector else None
        name = _text(name_el) or _text(card.find(["h1", "h2", "h3", "h4"])) or _text(card)
        name = name.strip()
        if not name:
            continue

        price_el = card.select_one(listing.price_selector)
        price_value, currency = parse_price(_text(price_el))

        link_el = card.select_one(listing.link_selector)
        href = link_el.get("href") if isinstance(link_el, Tag) else None
        product_url = urljoin(base_url, href) if href else None

        key = (name, product_url)
        if key in seen:
            continue
        seen.add(key)

        products.append(
            ScrapedProduct(
                name=name,
                price_value=price_value,
                price_currency=currency,
                product_url=product_url,
            )
        )

    return products


def find_next_page(html: str, base_url: str, selector: str | None) -> str | None:
    if not selector:
        return None
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one(selector)
    if not isinstance(el, Tag):
        return None
    # "Load more" buttons often stash the next-page URL in a data-* attribute
    # because the click is handled in JavaScript rather than the anchor's href.
    href = (
        el.get("href")
        or el.get("data-href")
        or el.get("data-url")
        or el.get("data-next-page")
        or el.get("data-next")
    )
    if not href or href in ("#", "javascript:void(0)"):
        return None
    return urljoin(base_url, href)
