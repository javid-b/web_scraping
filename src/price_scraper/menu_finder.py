"""Heuristic detector for site navigation menus.

Given a homepage HTML, find groups of anchors that look like category
navigation (lots of links sharing a common parent container with a nav-like
class or tag). Returns ranked suggestions so the user can pick one and paste
the URLs into `discovery.category_urls`.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)


# URL fragments that mean "not a category" — account/cart/footer/policy stuff.
_NOISE_PATHS = re.compile(
    r"/(?:"
    r"login|signin|signup|register|logout|account|profile|wishlist|favou?rite|"
    r"cart|basket|checkout|order|payment|delivery|shipping|return|warranty|"
    r"search|filter|sort|"
    r"contact|about|career|career?|vacancy|partner|store|location|branch|"
    r"news|blog|article|press|media|"
    r"faq|help|support|terms|privacy|cookie|legal|condition|policy|gdpr|"
    r"sitemap|robots|"
    r"compare|"
    r"language|currency|"
    r"facebook|instagram|twitter|youtube|telegram|whatsapp|tiktok|linkedin"
    r")(?:/|$|\.|\-|_)",
    re.IGNORECASE,
)

_CONTAINER_TAGS = {"nav", "ul", "ol"}
_MENU_CLASS_HINT = re.compile(r"\b(menu|nav(?!igation-link)|catalog|categor)", re.I)
_FOOTER_TAGS = {"footer"}
_BAD_CLASS = re.compile(r"\b(footer|social|lang|currency|share)", re.I)


@dataclass
class MenuSuggestion:
    selector: str             # CSS selector for the anchors inside the menu
    urls: list[str]           # de-duplicated absolute category URLs found
    note: str                 # human-readable explanation
    container_tag: str = ""
    container_classes: list[str] = field(default_factory=list)


def _is_plausible_category_url(url: str, base_netloc: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc.lstrip("www.") != base_netloc.lstrip("www."):
        return False
    path = parsed.path or "/"
    if path in ("", "/", "/index.html", "/home"):
        return False
    if _NOISE_PATHS.search(path):
        return False
    # Skip media/static assets and tracking endpoints.
    if re.search(r"\.(?:jpg|png|svg|gif|webp|pdf|mp4|css|js|ico|xml)(?:$|\?)", path, re.I):
        return False
    # Skip URLs with query strings — usually search/filter, not a category.
    if parsed.query:
        return False
    return True


def _container_selector(container: Tag) -> str:
    """Build a stable CSS selector for the menu container."""
    classes = [c for c in (container.get("class") or []) if not _BAD_CLASS.search(c)]
    tag = container.name
    if classes:
        # Use the longest / most specific class.
        cls = max(classes, key=len)
        return f"{tag}.{cls} a[href]"
    return f"{tag} a[href]"


def _find_stable_parent(a: Tag) -> Tag | None:
    """Walk up the DOM until we hit a recognisable menu container."""
    cur: Tag | None = a
    for _ in range(8):
        cur = cur.parent if cur else None
        if not isinstance(cur, Tag):
            return None
        if cur.name in _CONTAINER_TAGS:
            return cur
        classes = cur.get("class") or []
        if any(_MENU_CLASS_HINT.search(c) for c in classes):
            return cur
    return None


def find_menus(html: str, base_url: str, max_results: int = 3) -> list[MenuSuggestion]:
    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc

    # 1. Collect plausible category anchors.
    plausible: list[tuple[Tag, str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(base_url, href)
        if not _is_plausible_category_url(full, base_netloc):
            continue
        text = a.get_text(" ", strip=True)
        if not text or len(text) > 60 or len(text) < 2:
            continue
        plausible.append((a, full, text))

    # 2. Group anchors by their menu-like ancestor.
    groups: dict[int, list[tuple[str, str]]] = defaultdict(list)
    containers: dict[int, Tag] = {}
    for a, url, text in plausible:
        parent = _find_stable_parent(a)
        if parent is None:
            continue
        cid = id(parent)
        groups[cid].append((url, text))
        containers[cid] = parent

    # 3. Score each group.
    scored: list[tuple[float, Tag, list[str]]] = []
    for cid, items in groups.items():
        urls = list(dict.fromkeys(url for url, _ in items))  # de-dupe, keep order
        if len(urls) < 3:
            continue
        container = containers[cid]
        score = float(len(urls))
        if container.name == "nav":
            score += 5
        classes = container.get("class") or []
        if any(re.search(r"main|primary|top|header|catalog", c, re.I) for c in classes):
            score += 3
        if any(_BAD_CLASS.search(c) for c in classes):
            score -= 5
        if container.find_parent(_FOOTER_TAGS):
            score -= 10
        # Bonus when most URLs share a common path prefix (e.g. /category/X).
        prefixes = {urlparse(u).path.split("/", 2)[1] for u in urls if "/" in urlparse(u).path[1:]}
        if len(prefixes) == 1:
            score += 3
        scored.append((score, container, urls))

    scored.sort(key=lambda x: -x[0])

    out: list[MenuSuggestion] = []
    seen_url_sets: list[set[str]] = []
    for score, container, urls in scored:
        url_set = set(urls)
        # Drop suggestions that are a subset of a higher-ranked one.
        if any(url_set <= existing for existing in seen_url_sets):
            continue
        seen_url_sets.append(url_set)

        classes = [c for c in (container.get("class") or [])]
        note = f"<{container.name}>" + (f" .{classes[0]}" if classes else "")
        out.append(
            MenuSuggestion(
                selector=_container_selector(container),
                urls=urls,
                note=note,
                container_tag=container.name,
                container_classes=classes,
            )
        )
        if len(out) >= max_results:
            break
    return out


def render_menu_suggestions(suggestions: list[MenuSuggestion]) -> str:
    if not suggestions:
        return (
            "No navigation menu detected. The site may render its menu in "
            "JavaScript, or the structure is unusual. Open the homepage, "
            "right-click the menu → Inspect, and paste a CSS selector into "
            "`discovery.menu_selector` manually."
        )

    lines: list[str] = []
    for i, s in enumerate(suggestions, 1):
        lines.append(f"\n=== Menu candidate {i} — {len(s.urls)} links ({s.note}) ===")
        lines.append("Either set this as a dynamic selector:")
        lines.append("")
        lines.append("  discovery:")
        lines.append("    mode: menu")
        lines.append(f'    menu_selector: "{s.selector}"')
        lines.append("")
        lines.append("...or paste the discovered URLs directly into a static list:")
        lines.append("")
        lines.append("  discovery:")
        lines.append("    mode: static")
        lines.append("    category_urls:")
        for u in s.urls:
            lines.append(f"      - {u}")
    return "\n".join(lines)
