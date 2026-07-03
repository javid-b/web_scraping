"""Lego catalogue and assembly-manual generator.

Turns a voxel model (a set of unit-cube stud positions) into:
  * a shopping list ("catalogue") of Lego bricks needed to build it, and
  * a step-by-step PDF assembly manual.
"""

from .types import BrickType, PlacedBrick

__all__ = ["BrickType", "PlacedBrick"]
