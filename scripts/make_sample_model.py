"""Generate sample_data/model_example.json: a small 3-color tower with a flat
roof slab and a chimney, used to exercise multi-color solving, layering, and
the stud-connection stability check end-to-end.
"""

import json
import os

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "sample_data", "model_example.json")


def main():
    voxels = []

    # Walls/tower: 8 x 6 footprint, 4 layers tall, red.
    for x in range(8):
        for y in range(6):
            for z in range(4):
                voxels.append({"x": x, "y": y, "z": z, "color": "red"})

    # Flat roof slab: one layer, full footprint, blue.
    for x in range(8):
        for y in range(6):
            voxels.append({"x": x, "y": y, "z": 4, "color": "blue"})

    # Chimney: 2x2 footprint, 2 layers tall, yellow, sitting on the roof.
    for x in range(1, 3):
        for y in range(1, 3):
            for z in range(5, 7):
                voxels.append({"x": x, "y": y, "z": z, "color": "yellow"})

    model = {"name": "Sample Tower with Roof and Chimney", "voxels": voxels}
    with open(OUT_PATH, "w") as f:
        json.dump(model, f, indent=2)
    print(f"Wrote {len(voxels)} voxels to {OUT_PATH}")


if __name__ == "__main__":
    main()
