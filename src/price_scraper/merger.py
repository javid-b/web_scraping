from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from .config import MergeConfig
from .storage import Storage

log = logging.getLogger(__name__)


_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")

# Azerbaijani letters that don't decompose to ASCII via NFKD.
_AZ_TRANSLIT = str.maketrans({
    "ə": "e", "Ə": "e",
    "ş": "s", "Ş": "s",
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "İ": "i",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
})


def normalize(name: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    translit = name.translate(_AZ_TRANSLIT)
    nfkd = unicodedata.normalize("NFKD", translit)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_ = ascii_.lower()
    ascii_ = _NON_ALNUM.sub(" ", ascii_)
    return _WS.sub(" ", ascii_).strip()


@dataclass
class _Item:
    shop_id: str
    raw_name: str
    norm_name: str


def _cluster(items: list[_Item], threshold: int) -> list[list[int]]:
    """Greedy single-link clustering by token_set_ratio similarity.

    Returns indices grouped into clusters. Items already in a cluster are
    skipped, so each item ends up in exactly one cluster.
    """
    n = len(items)
    cluster_of = [-1] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if cluster_of[i] != -1:
            continue
        cid = len(clusters)
        clusters.append([i])
        cluster_of[i] = cid
        # Compare against every later item that isn't yet clustered.
        for j in range(i + 1, n):
            if cluster_of[j] != -1:
                continue
            score = fuzz.token_set_ratio(items[i].norm_name, items[j].norm_name)
            if score >= threshold:
                clusters[cid].append(j)
                cluster_of[j] = cid
    return clusters


def merge(storage: Storage, cfg: MergeConfig) -> int:
    """Cluster all (shop, product_name) pairs and persist the assignment.

    Returns the number of clusters created.
    """
    pairs = storage.distinct_products()
    items: list[_Item] = []
    for shop_id, name in pairs:
        norm = normalize(name)
        if len(norm) < cfg.min_name_length:
            continue
        items.append(_Item(shop_id=shop_id, raw_name=name, norm_name=norm))

    if not items:
        storage.replace_clusters([])
        return 0

    clusters = _cluster(items, cfg.fuzzy_threshold)

    rows: list[tuple[int, str, str, str]] = []
    for cid, member_ix in enumerate(clusters):
        members = [items[i] for i in member_ix]
        canonical = max(members, key=lambda m: len(m.raw_name)).raw_name
        for m in members:
            rows.append((cid, m.shop_id, m.raw_name, canonical))

    storage.replace_clusters(rows)
    log.info("merged %d products into %d clusters", len(items), len(clusters))
    return len(clusters)
