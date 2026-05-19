"""Heuristic CSS-selector detector for product-listing pages.

Given a category-page HTML, find:
  * the most likely "product card" class (repeating siblings containing a price),
  * a name selector inside the card,
  * a price selector inside the card,
and rank candidate layouts so the user can pick one.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from bs4 import BeautifulSoup, Tag

from .config import RequestConfig, ShopConfig
from .fetcher import Fetcher
from .parser import parse_price

log = logging.getLogger(__name__)


# Detects "looks like a price string" — used to filter card candidates.
PRICE_LIKE = re.compile(r"\d[\d\s.,]*\s*(?:₼|AZN|MAN|USD|EUR|RUB|\$|€|₽)", re.IGNORECASE)

# Generic layout classes we don't want as the card selector.
GENERIC_CLASSES = {
    "container", "wrapper", "main", "row", "col", "page", "content",
    "body", "section", "block", "list", "grid", "items", "products",
}


@dataclass
class Suggestion:
    product_selector: str
    name_selector: str | None
    price_selector: str
    product_count: int
    price_match_count: int
    samples: list[tuple[str, str]] = field(default_factory=list)  # (name, price text)


def _classes_of(el: Tag) -> list[str]:
    return list(el.get("class") or [])


def _avg_depth(els: list[Tag], sample: int = 5) -> float:
    """Mean DOM depth of the first `sample` elements (root = depth 0)."""
    total = 0
    n = min(len(els), sample)
    for el in els[:n]:
        depth = 0
        cur = el.parent
        while cur is not None:
            depth += 1
            cur = cur.parent
        total += depth
    return total / n if n else 0.0


def _find_card_groups(soup: BeautifulSoup, min_count: int = 4) -> list[tuple[str, list[Tag]]]:
    """Find class names that appear on >=min_count elements, where most of those
    elements contain price-like text. Sorted best-first."""
    by_class: dict[str, list[Tag]] = defaultdict(list)
    for el in soup.find_all(True, class_=True):
        for c in _classes_of(el):
            by_class[c].append(el)

    scored: list[tuple[str, list[Tag], int]] = []
    for cls, els in by_class.items():
        if len(els) < min_count or cls in GENERIC_CLASSES:
            continue
        price_count = sum(
            1 for el in els if PRICE_LIKE.search(el.get_text(" ", strip=True))
        )
        if price_count < len(els) * 0.5:
            continue
        scored.append((cls, els, price_count))

    # Rank: more matched prices > more elements > shallower DOM depth (outer wrapper).
    scored.sort(key=lambda x: (-x[2], -len(x[1]), _avg_depth(x[1])))
    return [(cls, els) for cls, els, _ in scored]


def _candidate_inner_selectors(
    cards: list[Tag], predicate: Callable[[Tag], bool]
) -> list[str]:
    """Collect class- and tag-based selectors from the first few cards where
    `predicate(el)` holds. Sorted so iteration order is deterministic across
    platforms (set iteration order can differ on Windows vs Linux)."""
    selectors: set[str] = set()
    for sample in cards[:3]:
        for el in sample.find_all(True):
            if not predicate(el):
                continue
            for c in _classes_of(el):
                selectors.add(f".{c}")
            if el.name in {"h1", "h2", "h3", "h4"}:
                selectors.add(el.name)
    return sorted(selectors)


def _score_selector(
    cards: list[Tag], selector: str, validate: Callable[[str], bool]
) -> tuple[int, int, float]:
    """Return (valid_match_count, distinct_text_count, -avg_text_length).

    * matches: more is better.
    * distinct: real names/prices vary per card; button labels repeat.
    * -avg_len: tiebreak prefers leaf elements (".price") over wrappers
      (".price-wrap" with old + new price concatenated).
    """
    good = 0
    seen: set[str] = set()
    total_len = 0
    for card in cards:
        matches = card.select(selector)
        if not matches:
            continue
        text = matches[0].get_text(" ", strip=True)
        if validate(text):
            good += 1
            seen.add(text)
            total_len += len(text)
    avg_len = (total_len / good) if good else 0.0
    return good, len(seen), -avg_len


def _best_inner_selector(
    cards: list[Tag],
    predicate: Callable[[Tag], bool],
    validate: Callable[[str], bool],
    threshold: float = 0.5,
) -> str | None:
    best: str | None = None
    best_key: tuple[int, int, float] = (0, 0, 0.0)
    for sel in _candidate_inner_selectors(cards, predicate):
        key = _score_selector(cards, sel, validate)
        if key > best_key:
            best, best_key = sel, key
    if best_key[0] < len(cards) * threshold:
        return None
    return best


def _is_price_text(text: str) -> bool:
    v, _ = parse_price(text)
    return v is not None and v > 0


def _is_name_text(text: str) -> bool:
    if len(text) < 4 or len(text) > 200:
        return False
    if not re.search(r"[A-Za-zƏəŞşÇçĞğÜüÖöIı]", text):
        return False
    # Reject pure price strings, but allow names that happen to contain a model
    # number ("MacBook Air M2 13\" 256GB"). A name is "price-like" only if it
    # has an actual currency token or is mostly digits/punctuation.
    if PRICE_LIKE.search(text):
        return False
    digits = sum(1 for c in text if c.isdigit())
    if digits >= len(text) * 0.4:
        return False
    return True


def suggest(html: str, max_results: int = 3) -> list[Suggestion]:
    soup = BeautifulSoup(html, "lxml")
    suggestions: list[Suggestion] = []
    used_classes: set[str] = set()

    for cls, cards in _find_card_groups(soup):
        # Skip if these cards live inside a class we've already suggested
        # (i.e. they're the inner half of a card we already picked).
        if any(
            card.find_parent(class_=other)
            for card in cards[:3]
            for other in used_classes
        ):
            continue

        price_sel = _best_inner_selector(
            cards,
            predicate=lambda el: bool(PRICE_LIKE.search(el.get_text(" ", strip=True))),
            validate=_is_price_text,
        )
        if not price_sel:
            continue

        name_sel = _best_inner_selector(
            cards,
            predicate=lambda el: _is_name_text(el.get_text(" ", strip=True)),
            validate=_is_name_text,
        )

        samples: list[tuple[str, str]] = []
        for card in cards[:5]:
            name_el = card.select_one(name_sel) if name_sel else None
            price_el = card.select_one(price_sel)
            name_text = (
                name_el.get_text(" ", strip=True)
                if name_el
                else card.get_text(" ", strip=True)
            )[:80]
            price_text = price_el.get_text(" ", strip=True) if price_el else ""
            samples.append((name_text, price_text))

        suggestions.append(
            Suggestion(
                product_selector=f".{cls}",
                name_selector=name_sel,
                price_selector=price_sel,
                product_count=len(cards),
                price_match_count=_score_selector(cards, price_sel, _is_price_text)[0],
                samples=samples,
            )
        )
        used_classes.add(cls)
        if len(suggestions) >= max_results:
            break

    return suggestions


def suggest_from_url(
    shop: ShopConfig | None, url: str, max_results: int = 3
) -> list[Suggestion]:
    fetcher = Fetcher(shop.request if shop else RequestConfig())
    html = fetcher.get(url)
    return suggest(html, max_results=max_results)


def render_suggestions(suggestions: list[Suggestion]) -> str:
    if not suggestions:
        return (
            "No product layouts detected. Either the page is JavaScript-rendered "
            "(check 'View Source' — if you don't see product names there, the\n"
            "scraper won't either and you need Playwright), or product cards on this\n"
            "page don't contain price text (price might load over AJAX)."
        )

    lines: list[str] = []
    for i, s in enumerate(suggestions, 1):
        lines.append(
            f"\n=== Layout {i} — {s.product_count} cards, "
            f"{s.price_match_count} with valid price ==="
        )
        lines.append("Paste under this shop's `listing:` block in shops.yaml:")
        lines.append("")
        lines.append("  listing:")
        lines.append(f'    product_selector: "{s.product_selector}"')
        if s.name_selector:
            lines.append(f'    name_selector:    "{s.name_selector}"')
        lines.append(f'    price_selector:   "{s.price_selector}"')
        lines.append("")
        lines.append("  Sample extraction:")
        for name, price in s.samples:
            lines.append(f"    {price:>20}   {name}")
    return "\n".join(lines)
