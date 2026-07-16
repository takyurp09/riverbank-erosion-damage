#!/usr/bin/env python3
"""JRC GSW land gain (accretion) exports masked to river buffer → upazila zonal CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gee_utils import load_config, load_upazila_fc, river_buffer_geometry

DRIVE_FOLDER = "riverbank_erosion_jrc_gain_river"
PIXEL_HA = 30 * 30 / 10_000


def jrc_land_gain_fn(yearly):
    import ee

    def water_class_year(y: int):
        return yearly.filter(ee.Filter.calendarRange(y, y, "year")).first().select("waterClass")

    def annual_land_gain(y: int):
        # water (2/3) in year t → land (1) in year t+1
        return water_class_year(y).gt(1).And(water_class_year(y + 1).eq(1)).rename("gain")

    return annual_land_gain


def queue_exports(project_id: str, cfg: dict, years: list[int]) -> None:
    import ee

    ee.Initialize(project=project_id)
    bb = cfg["bbox"]
    aoi = ee.Geometry.Rectangle([bb["west"], bb["south"], bb["east"], bb["north"]])
    river_zone = river_buffer_geometry(cfg, aoi)
    yearly = ee.ImageCollection(cfg["gee"]["jrc_collection"])
    annual_gain = jrc_land_gain_fn(yearly)
    upazilas = load_upazila_fc(cfg)
    scale = cfg["gee"]["export_scale_m"]

    for y in years:
        gain = annual_gain(y).clip(river_zone)
        stats = gain.reduceRegions(
            collection=upazilas, reducer=ee.Reducer.sum(), scale=scale, tileScale=4
        ).map(
            lambda f: f.set(
                {
                    "year": y,
                    "gain_pixels": f.get("sum"),
                    "gain_ha": ee.Number(f.get("sum")).multiply(PIXEL_HA),
                }
            )
        )
        desc = f"jrc_river_gain_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")

    print(f"\nQueued {len(years)} JRC gain exports → Drive/{DRIVE_FOLDER}/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--years", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    start = cfg["gee"]["years_start"]
    end = cfg["gee"]["years_end"]
    years = [int(y.strip()) for y in args.years.split(",")] if args.years else list(range(start, end))

    if args.dry_run:
        print(f"JRC gain river-masked: {years[0]}–{years[-1]}")
        return

    if not project_id:
        print("ERROR: set gee.project_id", file=sys.stderr)
        sys.exit(1)

    queue_exports(project_id, cfg, years)


if __name__ == "__main__":
    main()
