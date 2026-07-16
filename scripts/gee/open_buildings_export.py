#!/usr/bin/env python3
"""Week 3: Google Open Buildings — count + footprint per upazila (raster zonal)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gee_utils import load_config, load_upazila_fc, river_buffer_geometry

DRIVE_FOLDER = "riverbank_erosion_buildings"
BUILDINGS = "GOOGLE/Research/open-buildings/v3/polygons"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]

    if args.dry_run:
        print(f"Open Buildings raster zonal → {DRIVE_FOLDER}")
        return

    import ee

    ee.Initialize(project=project_id)
    bb = cfg["bbox"]
    aoi = ee.Geometry.Rectangle([bb["west"], bb["south"], bb["east"], bb["north"]])
    upazilas = load_upazila_fc(cfg)
    river_buf = river_buffer_geometry(cfg, aoi)

    buildings = ee.FeatureCollection(BUILDINGS).filterBounds(river_buf)

    # Raster zonal stats — much faster than per-upazila FC .size()
    count_img = ee.Image().byte().paint(buildings, 1).clip(river_buf).unmask(0).rename("bldg")
    footprint_img = (
        buildings.reduceToImage(properties=["area_in_meters"], reducer=ee.Reducer.sum())
        .clip(river_buf)
        .unmask(0)
        .rename("footprint_m2")
    )
    stack = count_img.addBands(footprint_img)

    stats = (
        stack.reduceRegions(
            collection=upazilas,
            reducer=ee.Reducer.sum(),
            scale=30,
            tileScale=8,
        )
        .map(
            lambda f: f.set(
                {
                    "n_buildings": f.get("bldg_sum"),
                    "footprint_m2": f.get("footprint_m2_sum"),
                    "year": 2023,
                }
            )
        )
    )

    ee.batch.Export.table.toDrive(
        collection=stats,
        description="open_buildings_upazila",
        folder=DRIVE_FOLDER,
        fileNamePrefix="open_buildings_upazila",
        fileFormat="CSV",
    ).start()
    print("Started: open_buildings_upazila (raster zonal, river-buffer clip)")


if __name__ == "__main__":
    main()
