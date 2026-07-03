"""Loaders for voxel models and brick libraries.

Voxel model format (JSON)::

    {
      "name": "my model",
      "voxels": [
        {"x": 0, "y": 0, "z": 0, "color": "red"},
        {"x": 1, "y": 0, "z": 0, "color": "red"}
      ]
    }

A CSV variant is also accepted with header ``x,y,z,color`` (color optional,
defaults to "any").

Brick library format (JSON)::

    {
      "bricks": [
        {"name": "Brick 2x4", "l": 2, "w": 4, "h": 1},
        {"name": "Brick 1x1", "l": 1, "w": 1, "h": 1}
      ]
    }

A library MUST contain a 1x1x1 brick -- it is the fallback piece used to
fill in gaps that no larger brick can cover.
"""

import csv
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .types import BrickType


@dataclass
class VoxelModel:
    name: str
    # (x, y, z) -> color, already offset so min corner is (0, 0, 0)
    voxels: Dict[Tuple[int, int, int], str]
    dims: Tuple[int, int, int]  # (X, Y, Z) size of the bounding grid
    origin_offset: Tuple[int, int, int]  # offset subtracted from raw input coords


def load_voxel_model(path: str) -> VoxelModel:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        raw = _load_voxels_json(path)
    elif ext == ".csv":
        raw = _load_voxels_csv(path)
    else:
        raise ValueError(f"Unsupported voxel model file type: {ext} (use .json or .csv)")

    name, entries = raw
    if not entries:
        raise ValueError(f"Voxel model {path!r} contains no voxels")

    xs = [e[0] for e in entries]
    ys = [e[1] for e in entries]
    zs = [e[2] for e in entries]
    min_x, min_y, min_z = min(xs), min(ys), min(zs)
    max_x, max_y, max_z = max(xs), max(ys), max(zs)

    voxels: Dict[Tuple[int, int, int], str] = {}
    for x, y, z, color in entries:
        key = (x - min_x, y - min_y, z - min_z)
        if key in voxels:
            raise ValueError(f"Duplicate voxel at {key} in {path!r}")
        voxels[key] = color

    dims = (max_x - min_x + 1, max_y - min_y + 1, max_z - min_z + 1)
    return VoxelModel(name=name, voxels=voxels, dims=dims, origin_offset=(min_x, min_y, min_z))


def _load_voxels_json(path: str):
    with open(path, "r") as f:
        data = json.load(f)
    name = data.get("name", os.path.basename(path))
    entries = []
    for v in data["voxels"]:
        entries.append((int(v["x"]), int(v["y"]), int(v["z"]), str(v.get("color", "any"))))
    return name, entries


def _load_voxels_csv(path: str):
    entries = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append((
                int(row["x"]), int(row["y"]), int(row["z"]),
                str(row.get("color") or "any"),
            ))
    return os.path.basename(path), entries


def load_brick_library(path: str) -> List[BrickType]:
    with open(path, "r") as f:
        data = json.load(f)
    bricks = [BrickType(name=b["name"], l=int(b["l"]), w=int(b["w"]), h=int(b.get("h", 1)))
              for b in data["bricks"]]
    if not any(b.l == 1 and b.w == 1 and b.h == 1 for b in bricks):
        raise ValueError(
            "Brick library must include a 1x1x1 brick, used as the fallback "
            "piece for gaps no larger brick can cover."
        )
    return bricks
