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
# Match menu-related substrings anywhere in a class name — no word boundary,
# so camelCase like `contentMenu`, `mainMenu`, `MegaCatalogNav` all match.
_MENU_CLASS_HINT = re.compile(r"(menu|nav|catalog|categor|drawer|dropdown)", re.I)
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


def _common_anchor_class(anchors: list[Tag]) -> str | None:
    """If every anchor in the group shares a class, return the longest one.

    On sites like kontakt where all subcategory links use the same class
    (`contentMenu__title`), this lets the suggested selector be precise
    (`a.contentMenu__title[href]`) without depending on the container.
    """
    if not anchors:
        return None
    common: set[str] | None = None
    for a in anchors:
        classes = set(a.get("class") or [])
        common = classes if common is None else common & classes
        if not common:
            return None
    return max(common, key=len) if common else None


def _build_selector(anchors: list[Tag], container: Tag) -> str:
    """Prefer a precise anchor selector when all links share a class."""
    shared = _common_anchor_class(anchors)
    if shared:
        return f"a.{shared}[href]"
    classes = [c for c in (container.get("class") or []) if not _BAD_CLASS.search(c)]
    tag = container.name
    if classes:
        cls = max(classes, key=len)
        return f"{tag}.{cls} a[href]"
    return f"{tag} a[href]"


def _menu_ancestors(a: Tag, max_levels: int = 8) -> list[Tag]:
    """All menu-like ancestors of `a` (innermost first), up to max_levels."""
    out: list[Tag] = []
    cur: Tag | None = a.parent if isinstance(a.parent, Tag) else None
    levels = 0
    while isinstance(cur, Tag) and levels < max_levels:
        if cur.name in _CONTAINER_TAGS:
            out.append(cur)
        else:
            classes = cur.get("class") or []
            if any(_MENU_CLASS_HINT.search(c) for c in classes):
                out.append(cur)
        cur = cur.parent
        levels += 1
    return out


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

    # 2. Group anchors by (tag, class signature) of EVERY menu-like ancestor in
    # their chain. The same anchor contributes to multiple groups, one per
    # ancestor — that way `<a>` deep inside a wrapper-per-item layout (kontakt:
    # .contentMenu__item one-per-anchor → .contentMenu shared by all) gets
    # grouped both ways and we can rank.
    Signature = tuple[str, tuple[str, ...]]  # (tag, sorted classes)
    groups: dict[Signature, list[tuple[Tag, str]]] = defaultdict(list)
    representatives: dict[Signature, Tag] = {}
    for a, url, text in plausible:
        seen: set[Signature] = set()
        for anc in _menu_ancestors(a):
            sig = (anc.name, tuple(sorted(anc.get("class") or [])))
            if sig in seen:
                continue
            seen.add(sig)
            groups[sig].append((a, url))
            representatives.setdefault(sig, anc)

    # 3. Score each group.
    # Each entry is (score, has_shared_anchor_class, container, anchors, urls).
    scored: list[tuple[float, bool, Tag, list[Tag], list[str]]] = []
    for sig, items in groups.items():
        anchors = [a for a, _ in items]
        urls = list(dict.fromkeys(url for _, url in items))
        if len(urls) < 3:
            continue
        container = representatives[sig]
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
        # Big penalty for catch-all groups (likely whole-page <ul> wrappers).
        if len(urls) > 200:
            score -= 50
        has_shared = _common_anchor_class(anchors) is not None
        if has_shared:
            score += 10
        # Bonus when URLs share a common path prefix (e.g. /category/X).
        prefixes = {urlparse(u).path.split("/", 2)[1] for u in urls if "/" in urlparse(u).path[1:]}
        if len(prefixes) == 1:
            score += 3
        scored.append((score, has_shared, container, anchors, urls))

    # Sort: shared-anchor-class candidates first (cohesive = real menu),
    # then by descending score within each tier.
    scored.sort(key=lambda x: (-int(x[1]), -x[0]))

    out: list[MenuSuggestion] = []
    accepted_sets: list[set[str]] = []
    for _score, _has_shared, container, anchors, urls in scored:
        url_set = set(urls)
        # Drop candidates that are a strict subset OR strict superset of one
        # we've already accepted. The first wins (typically the most precise);
        # broader 'wrapper' candidates and inner duplicates both get filtered.
        if any(url_set <= existing or existing <= url_set for existing in accepted_sets):
            continue
        accepted_sets.append(url_set)

        classes = list(container.get("class") or [])
        note = f"<{container.name}>" + (f" .{classes[0]}" if classes else "")
        out.append(
            MenuSuggestion(
                selector=_build_selector(anchors, container),
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
