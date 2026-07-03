"""Aggregate placed bricks into a purchasable parts list."""

import csv
import json
from collections import Counter
from typing import Dict, List, Tuple

from .types import PlacedBrick

CatalogueKey = Tuple[str, int, int, int, str]  # name, l, w, h, color
Catalogue = Dict[CatalogueKey, int]


def build_catalogue(placements: List[PlacedBrick]) -> Catalogue:
    """Count how many of each (brick shape, color) are needed.

    Rotation is ignored for counting purposes -- a "Brick 2x4" placed
    rotated 90 degrees is still one "Brick 2x4" to purchase.
    """
    counter: Counter = Counter()
    for p in placements:
        key = (p.brick.name, p.brick.l, p.brick.w, p.brick.h, p.color)
        counter[key] += 1
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def print_catalogue(catalogue: Catalogue) -> None:
    total = sum(catalogue.values())
    name_w = max((len(k[0]) for k in catalogue), default=10)
    print(f"{'Brick':<{name_w}}  {'Size (LxWxH)':<14}  {'Color':<10}  Qty")
    print("-" * (name_w + 14 + 10 + 10))
    for (name, l, w, h, color), qty in catalogue.items():
        size = f"{l}x{w}x{h}"
        print(f"{name:<{name_w}}  {size:<14}  {color:<10}  {qty}")
    print("-" * (name_w + 14 + 10 + 10))
    print(f"Total pieces: {total}")


def save_catalogue_csv(catalogue: Catalogue, path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brick_name", "length", "width", "height", "color", "quantity"])
        for (name, l, w, h, color), qty in catalogue.items():
            writer.writerow([name, l, w, h, color, qty])


def save_catalogue_json(catalogue: Catalogue, path: str) -> None:
    rows = [
        {"brick_name": name, "length": l, "width": w, "height": h, "color": color, "quantity": qty}
        for (name, l, w, h, color), qty in catalogue.items()
    ]
    with open(path, "w") as f:
        json.dump({"parts": rows, "total_pieces": sum(catalogue.values())}, f, indent=2)
