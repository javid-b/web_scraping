"""Command-line entry point.

Example:
    python -m lego_catalogue.cli \\
        --model sample_data/model_example.json \\
        --library sample_data/brick_library.json \\
        --min-stud-connection 2 \\
        --bricks-per-step 1 \\
        --output-dir output
"""

import argparse
import os
import sys

from .catalogue import build_catalogue, print_catalogue, save_catalogue_csv, save_catalogue_json
from .io_utils import load_brick_library, load_voxel_model
from .manual import generate_pdf_manual
from .solver import solve

_DEFAULT_LIBRARY = os.path.join(os.path.dirname(__file__), "..", "sample_data", "brick_library.json")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a Lego parts catalogue and PDF assembly manual from a voxel model.")
    p.add_argument("--model", required=True, help="Path to voxel model (.json or .csv)")
    p.add_argument("--library", default=_DEFAULT_LIBRARY, help="Path to brick library JSON (default: bundled standard set)")
    p.add_argument("--min-stud-connection", type=int, default=2,
                   help="Minimum overlapping studs required between a brick and the single brick "
                        "supporting it below, for a stable joint (default: 2)")
    p.add_argument("--bricks-per-step", type=int, default=1,
                   help="How many bricks to introduce per manual page/step (default: 1)")
    p.add_argument("--output-dir", default="output", help="Directory to write catalogue + manual into")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    model = load_voxel_model(args.model)
    library = load_brick_library(args.library)

    print(f"Loaded model {model.name!r}: {len(model.voxels)} voxels, "
          f"bounding box {model.dims[0]}x{model.dims[1]}x{model.dims[2]}")

    result = solve(model, library, min_stud_connection=args.min_stud_connection)

    catalogue = build_catalogue(result.placements)
    print()
    print_catalogue(catalogue)

    if result.warnings:
        print(f"\n{len(result.warnings)} stability warning(s) -- see manual PDF for details.")

    csv_path = os.path.join(args.output_dir, "catalogue.csv")
    json_path = os.path.join(args.output_dir, "catalogue.json")
    pdf_path = os.path.join(args.output_dir, "manual.pdf")

    save_catalogue_csv(catalogue, csv_path)
    save_catalogue_json(catalogue, json_path)
    generate_pdf_manual(
        model_name=model.name,
        placements=result.placements,
        dims=result.dims,
        catalogue=catalogue,
        warnings=result.warnings,
        output_path=pdf_path,
        bricks_per_step=args.bricks_per_step,
    )

    print(f"\nWrote {csv_path}, {json_path}, {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
