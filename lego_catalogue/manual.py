"""Render a step-by-step PDF assembly manual, Lego-instruction-booklet style."""

from datetime import date
from typing import List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from .catalogue import Catalogue
from .types import PlacedBrick

# Basic color-name -> RGBA mapping. Unknown names fall back to a neutral gray.
_COLOR_MAP = {
    "red": "#c91a09", "blue": "#0055bf", "green": "#237841", "yellow": "#f2cd37",
    "white": "#f4f4f4", "black": "#1b2a34", "gray": "#9ba19d", "grey": "#9ba19d",
    "orange": "#fe8a18", "brown": "#582a12", "tan": "#e4cd9e", "purple": "#81007b",
    "lightgray": "#a0a5a9", "any": "#a0a5a9",
}


def _color_rgba(name: str, alpha: float) -> Tuple[float, float, float, float]:
    hex_color = _COLOR_MAP.get(name.lower(), "#a0a5a9")
    rgb = matplotlib.colors.to_rgb(hex_color)
    return (rgb[0], rgb[1], rgb[2], alpha)


def _chunk(items: List[PlacedBrick], size: int) -> List[List[PlacedBrick]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _draw_voxels(ax, dims, done_before: List[PlacedBrick], this_step: List[PlacedBrick]):
    X, Y, Z = dims
    filled = np.zeros((X, Y, Z), dtype=bool)
    facecolors = np.empty((X, Y, Z), dtype=object)

    for p in done_before:
        for (x, y, z) in p.voxels():
            filled[x, y, z] = True
            facecolors[x, y, z] = _color_rgba(p.color, 0.35)
    for p in this_step:
        for (x, y, z) in p.voxels():
            filled[x, y, z] = True
            facecolors[x, y, z] = _color_rgba(p.color, 0.95)

    ax.voxels(filled, facecolors=facecolors, edgecolor="#333333", linewidth=0.3)
    ax.set_xlim(0, X)
    ax.set_ylim(0, Y)
    ax.set_zlim(0, Z)
    ax.set_box_aspect((X, Y, max(Z, 1)))
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")


def _cover_page(pdf: PdfPages, model_name: str, n_pieces: int, n_steps: int, dims):
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
    fig.text(0.5, 0.65, "LEGO Assembly Manual", ha="center", fontsize=26, weight="bold")
    fig.text(0.5, 0.58, model_name, ha="center", fontsize=18)
    fig.text(0.5, 0.48, f"Model size: {dims[0]} x {dims[1]} x {dims[2]} studs", ha="center", fontsize=12)
    fig.text(0.5, 0.43, f"Total pieces: {n_pieces}", ha="center", fontsize=12)
    fig.text(0.5, 0.38, f"Build steps: {n_steps}", ha="center", fontsize=12)
    fig.text(0.5, 0.08, f"Generated {date.today().isoformat()}", ha="center", fontsize=9, color="gray")
    pdf.savefig(fig)
    plt.close(fig)


def _catalogue_page(pdf: PdfPages, catalogue: Catalogue):
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis("off")
    ax.set_title("Parts Needed", fontsize=18, weight="bold", pad=20)
    rows = [[name, f"{l}x{w}x{h}", color, str(qty)] for (name, l, w, h, color), qty in catalogue.items()]
    table = ax.table(
        cellText=rows,
        colLabels=["Brick", "Size", "Color", "Qty"],
        loc="upper center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    total = sum(catalogue.values())
    fig.text(0.5, 0.03, f"Total pieces: {total}", ha="center", fontsize=11, weight="bold")
    pdf.savefig(fig)
    plt.close(fig)


def _warnings_page(pdf: PdfPages, warnings: List[str]):
    if not warnings:
        return
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.5, 0.95, "Build Warnings", ha="center", fontsize=18, weight="bold")
    fig.text(0.5, 0.90, "The following joints are weaker than requested; reinforce by hand.",
             ha="center", fontsize=10, color="gray")
    y = 0.85
    for w in warnings[:60]:
        fig.text(0.06, y, f"- {w}", ha="left", fontsize=8, wrap=True)
        y -= 0.02
        if y < 0.03:
            break
    pdf.savefig(fig)
    plt.close(fig)


def generate_pdf_manual(
    model_name: str,
    placements: List[PlacedBrick],
    dims: Tuple[int, int, int],
    catalogue: Catalogue,
    warnings: List[str],
    output_path: str,
    bricks_per_step: int = 1,
    elev: float = 25,
    azim: float = -60,
) -> None:
    """Write a multi-page PDF: cover, parts list, warnings, then one page per build step."""
    steps = _chunk(placements, max(1, bricks_per_step))

    with PdfPages(output_path) as pdf:
        _cover_page(pdf, model_name, len(placements), len(steps), dims)
        _catalogue_page(pdf, catalogue)
        _warnings_page(pdf, warnings)

        done: List[PlacedBrick] = []
        for i, step in enumerate(steps, start=1):
            fig = plt.figure(figsize=(8.27, 11.69))
            ax = fig.add_subplot(111, projection="3d")
            ax.view_init(elev=elev, azim=azim)
            _draw_voxels(ax, dims, done, step)

            desc_lines = [f"{p.brick.name} ({p.l}x{p.w}x{p.brick.h}) at "
                          f"({p.x},{p.y},{p.z}){' [rotated]' if p.rotated else ''}, color={p.color}"
                          for p in step]
            fig.suptitle(f"Step {i} / {len(steps)}", fontsize=16, weight="bold", y=0.97)
            fig.text(0.5, 0.05, "\n".join(desc_lines[:10]), ha="center", fontsize=8)

            pdf.savefig(fig)
            plt.close(fig)
            done.extend(step)
