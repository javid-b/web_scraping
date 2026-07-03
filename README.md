# Lego Catalogue & Manual Generator

Turn a voxel model (a set of unit-cube stud positions) into:

1. A **parts catalogue** — which bricks to buy, and how many of each.
2. A **step-by-step PDF assembly manual**, in the style of an official Lego
   instruction booklet.

## How it works

The problem — tile an arbitrary 3D shape exactly using a library of
rectangular brick shapes, using as few pieces as possible, while keeping the
model structurally sound — is a form of 3D bin-packing / exact-cover and is
NP-hard in general. This tool uses a practical **greedy heuristic**
(`lego_catalogue/solver.py`) rather than an exact optimizer:

- Bricks are placed **bottom-up**, layer by layer, since a brick can only
  rest on bricks already placed beneath it.
- At each still-uncovered voxel, the solver tries the **largest-volume
  brick** from the library first (in both horizontal rotations), then
  smaller ones, accepting the first that: fits entirely inside the required
  region, matches the voxel's color, and meets the stability constraint
  below. Largest-first is the standard heuristic for minimizing piece count
  in box-covering problems.
- **Stability / minimum stud connection**: a brick placed at height `z > 0`
  must share at least `--min-stud-connection` overlapping studs with a
  *single* brick directly beneath it. This mirrors the real physical
  requirement that a joint needs enough overlapping studs to hold together,
  not just to be technically resting on something. Bricks on the base layer
  (`z == 0`) are always considered supported.
- If no library brick can satisfy the stability requirement at some voxel
  (e.g. a thin unsupported column in the source model, or a stud-connection
  requirement stricter than the geometry allows), the solver falls back to
  a **1x1x1 filler brick** and records a warning rather than failing. These
  warnings are printed to the console and listed in the PDF manual so you
  know exactly which joints to reinforce or redesign.

This won't always find the mathematically optimal minimum piece count, but
it always produces a valid, physically buildable layout (given the
stability constraint you choose), and it strongly favors big pieces over
lots of small ones.

### Assumptions / simplifications

- One voxel = one stud horizontally, and one standard brick height
  vertically. Thin "plates" (1/3 brick height) aren't modeled — if you need
  them, add library entries with fractional `h` conventions adapted to your
  own vertical unit and scale your model accordingly.
- Bricks are plain rectangular boxes (no slopes, arches, technic holes,
  etc.) and only rotate around the vertical axis (no standing bricks on
  end).
- Any brick shape is assumed purchasable in whatever color the model asks
  for. Real Lego doesn't sell every shape in every color — cross-check the
  generated catalogue against a parts marketplace (e.g. BrickLink/Rebrickable) before buying.
- "Connection strength" is modeled purely as vertical stud overlap with the
  single best-supporting brick below, which is the dominant factor in real
  Lego structural stability.

## Input formats

### Voxel model (`--model`, `.json` or `.csv`)

JSON:

```json
{
  "name": "my model",
  "voxels": [
    {"x": 0, "y": 0, "z": 0, "color": "red"},
    {"x": 1, "y": 0, "z": 0, "color": "red"}
  ]
}
```

CSV (header `x,y,z,color`, color optional):

```csv
x,y,z,color
0,0,0,red
1,0,0,red
```

Coordinates are integers; `x`/`y` are horizontal stud positions, `z` is the
vertical layer index. Coordinates don't need to start at 0 or be
non-negative — the loader auto-offsets to a 0-based bounding box.

### Brick library (`--library`, JSON)

```json
{
  "bricks": [
    {"name": "Brick 2x4", "l": 2, "w": 4, "h": 1},
    {"name": "Brick 1x1", "l": 1, "w": 1, "h": 1}
  ]
}
```

`l`/`w` are footprint studs, `h` is height in layer units (default 1). A
**1x1x1 brick is required** in every library — it's the universal fallback
filler. A ready-to-use standard set is bundled at
`sample_data/brick_library.json`.

## Usage

```bash
pip install -r requirements.txt

python3 -m lego_catalogue.cli \
    --model sample_data/model_example.json \
    --library sample_data/brick_library.json \
    --min-stud-connection 2 \
    --bricks-per-step 1 \
    --output-dir output
```

Outputs (in `--output-dir`):

- `catalogue.csv` / `catalogue.json` — the parts list to buy.
- `manual.pdf` — cover page, parts list page, any stability warnings, then
  one manual page per build step (a 3D render with previously-placed bricks
  faded and the newly-added brick(s) highlighted).

Flags:

- `--min-stud-connection N` (default 2): minimum overlapping studs required
  between a brick and its support below. Higher = sturdier but more
  1x1 fallback pieces on tricky geometry; `1` just requires *some* contact.
- `--bricks-per-step N` (default 1): how many bricks to introduce per manual
  page. Raise this for large models to keep the PDF shorter.

A sample model (a small tower with a flat roof and a 2-layer chimney, three
colors) is bundled at `sample_data/model_example.json`, generated by
`scripts/make_sample_model.py`.

## Possible extensions

- An exact/near-optimal solver (e.g. ILP via OR-Tools) for true minimum
  piece count on small models.
- Sloped/curved/technic piece support.
- Cross-referencing the generated catalogue against a live parts
  marketplace (BrickLink/Rebrickable) for pricing and purchase links.
- Support for plates (fractional brick height) as a distinct vertical unit.
