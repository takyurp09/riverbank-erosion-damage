#!/usr/bin/env python3
"""Sentinel-2 NDWI erosion (2yr persistence) masked to river buffer — robustness 2017–2023."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gee_utils import load_config, load_upazila_fc, river_buffer_geometry

DRIVE_FOLDER = "riverbank_erosion_s2_river"
PIXEL_HA = 10 * 10 / 10_000  # 10 m resolution


def dry_season_water(year: int, aoi):
    import ee

    col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    start = ee.Date.fromYMD(year, 11, 1)
    end = ee.Date.fromYMD(year + 1, 3, 1)

    def prep(img):
        scl = img.select("SCL")
        clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        ndwi = img.normalizedDifference(["B3", "B8"])
        return ndwi.updateMask(clear).rename("ndwi")

    return (
        col.filterDate(start, end)
        .filterBounds(aoi)
        .map(prep)
        .median()
        .gt(0)
        .rename("water")
    )


def queue_exports(project_id: str, cfg: dict, years: list[int]) -> None:
    import ee

    ee.Initialize(project=project_id)
    bb = cfg["bbox"]
    aoi = ee.Geometry.Rectangle([bb["west"], bb["south"], bb["east"], bb["north"]])
    river_zone = river_buffer_geometry(cfg, aoi)
    upazilas = load_upazila_fc(cfg)
    scale = 10

    for y in years:
        if y + 1 > max(years):
            continue
        loss = dry_season_water(y, aoi).Not().And(dry_season_water(y + 1, aoi)).rename("loss").clip(river_zone)
        stats = loss.reduceRegions(
            collection=upazilas, reducer=ee.Reducer.sum(), scale=scale, tileScale=4
        ).map(lambda f: f.set({"year": y, "loss_ha": ee.Number(f.get("sum")).multiply(PIXEL_HA)}))

        desc = f"s2_river_2yr_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")

    print(f"\nQueued {len([y for y in years if y + 1 <= max(years)])} S2 exports → Drive/{DRIVE_FOLDER}/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--years", default="2017,2018,2019,2020,2021,2022,2023")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y.strip()) for y in args.years.split(",")]

    if args.dry_run:
        print(f"S2 river 2yr: {years}")
        return

    queue_exports(project_id, cfg, years)


if __name__ == "__main__":
    main()
