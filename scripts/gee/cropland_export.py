#!/usr/bin/env python3
"""Week 3: cropland masks — WorldCover (static) + MODIS MCD12Q1 annual → upazila CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gee_utils import load_config, load_upazila_fc

DRIVE_FOLDER = "riverbank_erosion_cropland"
# IGBP class 12 = croplands; WorldCover class 40 = cropland
MODIS_CROPLAND = 12
WORLDCOVER_CROPLAND = 40


def queue_worldcover(project_id: str, cfg: dict) -> None:
    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)
    wc = (
        ee.ImageCollection("ESA/WorldCover/v200")
        .filterDate("2021-01-01", "2022-01-01")
        .first()
        .select("Map")
        .eq(WORLDCOVER_CROPLAND)
        .rename("cropland")
    )
    stats = (
        wc.reduceRegions(collection=upazilas, reducer=ee.Reducer.mean(), scale=100, tileScale=4)
        .map(lambda f: f.set({"year": 2021, "source": "worldcover"}))
    )
    ee.batch.Export.table.toDrive(
        collection=stats,
        description="cropland_worldcover_upazila",
        folder=DRIVE_FOLDER,
        fileNamePrefix="cropland_worldcover_upazila",
        fileFormat="CSV",
    ).start()
    print("Started: cropland_worldcover_upazila")


def queue_modis(project_id: str, cfg: dict, years: list[int]) -> None:
    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)
    modis = ee.ImageCollection("MODIS/061/MCD12Q1")

    for y in years:
        img = (
            modis.filter(ee.Filter.calendarRange(y, y, "year"))
            .first()
            .select("LC_Type1")
            .eq(MODIS_CROPLAND)
            .rename("cropland")
        )
        stats = (
            img.reduceRegions(collection=upazilas, reducer=ee.Reducer.mean(), scale=500, tileScale=4)
            .map(lambda f: f.set({"year": y, "source": "modis"}))
        )
        desc = f"cropland_modis_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--modis-only", action="store_true")
    parser.add_argument("--worldcover-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    modis_years = list(range(2001, 2015))

    if args.dry_run:
        print(f"Cropland exports: WorldCover + MODIS {modis_years[0]}–{modis_years[-1]}")
        return

    if not args.modis_only:
        queue_worldcover(project_id, cfg)
    if not args.worldcover_only:
        queue_modis(project_id, cfg, modis_years)


if __name__ == "__main__":
    main()
