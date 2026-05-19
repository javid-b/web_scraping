from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .inspect_tool import inspect
from .merger import merge
from .runner import run_all
from .storage import Storage
from .suggester import render_suggestions, suggest_from_url


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_scrape(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.shop:
        cfg.shops = [s for s in cfg.shops if s.id in set(args.shop)]
        if not cfg.shops:
            print(f"no shops match: {args.shop}", file=sys.stderr)
            return 2

    storage = Storage(cfg.storage.db_path)
    try:
        results = run_all(cfg, storage)
    finally:
        storage.close()

    print("\n=== scrape summary ===")
    for r in results:
        print(
            f"  {r.shop_id:>16}  categories={r.categories_visited:<4}  "
            f"pages={r.pages_fetched:<4}  stored={r.products_stored:<5}  "
            f"errors={len(r.errors)}"
        )
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    storage = Storage(cfg.storage.db_path)
    try:
        n = merge(storage, cfg.merge)
    finally:
        storage.close()
    print(f"clusters built: {n}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    by_id = {s.id: s for s in cfg.shops}
    if args.shop not in by_id:
        print(f"unknown shop id: {args.shop}", file=sys.stderr)
        return 2
    inspect(by_id[args.shop], args.url, limit=args.limit)
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    shop = None
    if args.shop:
        by_id = {s.id: s for s in cfg.shops}
        if args.shop not in by_id:
            print(f"unknown shop id: {args.shop}", file=sys.stderr)
            return 2
        shop = by_id[args.shop]
    suggestions = suggest_from_url(shop, args.url, max_results=args.limit)
    print(render_suggestions(suggestions))
    return 0 if suggestions else 1


def cmd_history(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    storage = Storage(cfg.storage.db_path)
    try:
        rows = storage.price_history(args.shop, args.product)
    finally:
        storage.close()
    if not rows:
        print("no history found")
        return 1
    print(f"price history: {args.shop} / {args.product}")
    for r in rows:
        price = r["price_value"]
        cur = r["price_currency"] or ""
        print(f"  {r['scraped_at']}   {price}  {cur}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="price_scraper", description="Daily multi-shop price scraper.")
    p.add_argument("--config", default="config/shops.yaml", type=Path, help="path to shops.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="run scrape across configured shops")
    s.add_argument("--shop", action="append", help="restrict to shop id (repeatable)")
    s.set_defaults(func=cmd_scrape)

    m = sub.add_parser("merge", help="cluster products across shops using fuzzy matching")
    m.set_defaults(func=cmd_merge)

    i = sub.add_parser("inspect", help="dry-run a single URL with a shop's selectors")
    i.add_argument("shop", help="shop id")
    i.add_argument("url", help="URL of a category page to test")
    i.add_argument("--limit", type=int, default=10)
    i.set_defaults(func=cmd_inspect)

    sg = sub.add_parser(
        "suggest",
        help="auto-detect product/name/price selectors for a category URL",
    )
    sg.add_argument("url", help="URL of a category page to analyze")
    sg.add_argument(
        "--shop",
        help="shop id whose UA/headers to use (otherwise default UA)",
    )
    sg.add_argument("--limit", type=int, default=3, help="how many candidate layouts to show")
    sg.set_defaults(func=cmd_suggest)

    h = sub.add_parser("history", help="print price history of a product in one shop")
    h.add_argument("shop")
    h.add_argument("product")
    h.set_defaults(func=cmd_history)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
