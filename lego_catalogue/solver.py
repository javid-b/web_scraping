"""Greedy brick-placement solver.

The problem of exactly tiling an arbitrary polycube with a library of
rectangular boxes while minimizing piece count is a form of exact-cover /
bin-packing and is NP-hard in general. This module implements a practical
greedy heuristic rather than an exact optimizer:

  * Bricks are placed bottom-up, one voxel-layer (z) at a time, since a
    brick can only rest on bricks already placed below it.
  * At each still-uncovered voxel, the largest-volume brick (checked in both
    horizontal rotations) that fits entirely within the required region,
    matches the voxel's color, and meets the minimum stud-overlap/support
    constraint is placed. Largest-first is a standard, effective heuristic
    for minimizing piece count in rectangle/box-covering problems.
  * "Support" for a brick at z > 0 is defined as the largest number of studs
    of its footprint that land on a single already-placed brick directly
    below it (z - 1). This mirrors the real-world physical requirement that
    a brick needs enough overlapping studs with the piece(s) below it to be
    a stable connection, not just resting loosely.
  * If no brick satisfies the support requirement (e.g. a thin unsupported
    column in the source model), the solver falls back to the library's
    1x1x1 brick and records a warning rather than failing outright.

This will not always find the true minimum piece count, but it produces a
valid, physically buildable model (subject to the stability constraint) and
tends to prefer large bricks, which is usually what "as few pieces as
possible" means in practice.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .io_utils import VoxelModel
from .types import BrickType, PlacedBrick


@dataclass
class SolveResult:
    placements: List[PlacedBrick]
    warnings: List[str]
    dims: Tuple[int, int, int]


def _orientations(l: int, w: int):
    if l == w:
        return [(l, w)]
    return [(l, w), (w, l)]


def solve(
    model: VoxelModel,
    library: List[BrickType],
    min_stud_connection: int = 2,
) -> SolveResult:
    """Find a brick layout that covers `model.voxels`.

    Args:
        model: the voxel model to build (already offset to a 0-based grid).
        library: available brick shapes. Must include a 1x1x1 (enforced by
            io_utils.load_brick_library).
        min_stud_connection: minimum number of overlapping studs a brick
            must share with a single supporting brick beneath it (z > 0) to
            be considered a stable connection. Bricks resting on the base
            (z == 0) are always considered supported.

    Returns:
        SolveResult with the list of PlacedBrick, any stability warnings,
        and the grid dimensions used.
    """
    X, Y, Z = model.dims
    if min_stud_connection < 1:
        raise ValueError("min_stud_connection must be >= 1")

    required = np.zeros((X, Y, Z), dtype=bool)
    color_grid = np.full((X, Y, Z), "", dtype=object)
    for (x, y, z), color in model.voxels.items():
        required[x, y, z] = True
        color_grid[x, y, z] = color

    built = np.zeros((X, Y, Z), dtype=bool)
    placed_id = np.full((X, Y, Z), -1, dtype=np.int32)

    library_sorted = sorted(library, key=lambda b: b.volume, reverse=True)
    fallback_brick = next(b for b in library if b.l == 1 and b.w == 1 and b.h == 1)

    placements: List[PlacedBrick] = []
    warnings: List[str] = []
    ox, oy, oz = model.origin_offset

    def max_support(x: int, y: int, l: int, w: int, z: int) -> int:
        if z == 0:
            return -1  # sentinel: resting on the baseplate, always fine
        sub = placed_id[x:x + l, y:y + w, z - 1]
        ids = sub[sub >= 0]
        if ids.size == 0:
            return 0
        _, counts = np.unique(ids, return_counts=True)
        return int(counts.max())

    for z in range(Z):
        for y in range(Y):
            for x in range(X):
                if not required[x, y, z] or built[x, y, z]:
                    continue
                color = color_grid[x, y, z]
                chosen = None  # (brick, l, w)

                for brick in library_sorted:
                    if z + brick.h > Z:
                        continue
                    for (bl, bw) in _orientations(brick.l, brick.w):
                        if x + bl > X or y + bw > Y:
                            continue
                        box_req = required[x:x + bl, y:y + bw, z:z + brick.h]
                        if not box_req.all():
                            continue
                        box_built = built[x:x + bl, y:y + bw, z:z + brick.h]
                        if box_built.any():
                            continue
                        box_color = color_grid[x:x + bl, y:y + bw, z:z + brick.h]
                        if not np.all(box_color == color):
                            continue
                        support = max_support(x, y, bl, bw, z)
                        if support == -1 or support >= min_stud_connection:
                            chosen = (brick, bl, bw)
                            break
                    if chosen:
                        break

                if chosen is None:
                    # Fall back to the 1x1x1 filler brick, whatever support it gets.
                    support = max_support(x, y, 1, 1, z)
                    chosen = (fallback_brick, 1, 1)
                    if support not in (-1,) and support < min_stud_connection:
                        wx, wy, wz = x + ox, y + oy, z + oz
                        warnings.append(
                            f"Weak/unsupported connection at ({wx},{wy},{wz}): "
                            f"only {support} stud(s) of support "
                            f"(requested minimum {min_stud_connection}). "
                            f"Placed a 1x1 filler brick; reinforce this joint by hand."
                        )

                brick, bl, bw = chosen
                idx = len(placements)
                placements.append(PlacedBrick(
                    brick=brick, x=x, y=y, z=z, l=bl, w=bw, color=color,
                    rotated=(bl, bw) != (brick.l, brick.w), step=idx,
                ))
                built[x:x + bl, y:y + bw, z:z + brick.h] = True
                placed_id[x:x + bl, y:y + bw, z:z + brick.h] = idx

    return SolveResult(placements=placements, warnings=warnings, dims=(X, Y, Z))
