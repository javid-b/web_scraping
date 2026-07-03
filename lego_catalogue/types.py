"""Core data types shared across the package."""

from dataclasses import dataclass
from typing import Iterator, Tuple


@dataclass(frozen=True)
class BrickType:
    """A rectangular Lego brick/plate shape, in stud units.

    l, w are the horizontal footprint (in studs); h is the vertical size
    measured in "layer units" (1 layer unit = 1 voxel of the input model).
    """

    name: str
    l: int
    w: int
    h: int = 1

    def __post_init__(self):
        if self.l < 1 or self.w < 1 or self.h < 1:
            raise ValueError(f"BrickType {self.name!r} must have positive dimensions")

    @property
    def volume(self) -> int:
        return self.l * self.w * self.h

    @property
    def is_square(self) -> bool:
        return self.l == self.w


@dataclass
class PlacedBrick:
    """A BrickType placed at a specific grid position (grid-local coordinates)."""

    brick: BrickType
    x: int
    y: int
    z: int
    l: int  # footprint length actually used (after rotation)
    w: int  # footprint width actually used (after rotation)
    color: str
    rotated: bool
    step: int = 0

    @property
    def h(self) -> int:
        return self.brick.h

    def voxels(self) -> Iterator[Tuple[int, int, int]]:
        for dx in range(self.l):
            for dy in range(self.w):
                for dz in range(self.brick.h):
                    yield (self.x + dx, self.y + dy, self.z + dz)
