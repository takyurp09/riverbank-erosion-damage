#!/usr/bin/env python3
"""Landsat NDWI erosion masked to river buffer → upazila zonal CSV on GEE."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from gee_utils import load_config, load_upazila_fc, erosion_zone_geometry

ROOT = Path(__file__).resolve().parents[2]
DRIVE_FOLDER = "riverbank_erosion_landsat_river"
PIXEL_HA = 30 * 30 / 10_000


def landsat_merged():
    import ee

    return (
        ee.ImageCollection("LANDSAT/LT05/C02/T1_L2")
        .merge(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2"))
        .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
        .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
    )


def dry_season_water(year: int, collection, aoi):
    import ee

    start = ee.Date.fromYMD(year, 11, 1)
    end = ee.Date.fromYMD(year + 1, 3, 1)

    def prep(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = img.select(["SR_B3", "SR_B5"]).multiply(0.0000275).add(-0.2)
        ndwi = sr.normalizedDifference(["SR_B3", "SR_B5"])
        return ndwi.updateMask(clear)

    return (
        collection.filterDate(start, end)
        .filterBounds(aoi)
        .map(prep)
        .median()
        .gt(0)
        .rename("water")
    )


def export_loss(project_id: str, cfg: dict, years: list[int], persistent: bool) -> None:
    import ee

    ee.Initialize(project=project_id)
    bb = cfg["bbox"]
    aoi = ee.Geometry.Rectangle([bb["west"], bb["south"], bb["east"], bb["north"]])
    river_zone = erosion_zone_geometry(cfg, aoi)
    col = landsat_merged()
    upazilas = load_upazila_fc(cfg)
    scale = cfg["gee"]["export_scale_m"]
    tag = "2yr" if persistent else "1yr"

    for y in years:
        if persistent:
            if y + 1 > max(years):
                continue
            loss = dry_season_water(y, col, aoi).Not().And(dry_season_water(y + 1, col, aoi))
        else:
            loss = dry_season_water(y - 1, col, aoi).Not().And(dry_season_water(y, col, aoi))

        loss = loss.rename("loss").clip(river_zone)

        stats = (
            loss.reduceRegions(collection=upazilas, reducer=ee.Reducer.sum(), scale=scale, tileScale=4)
            .map(lambda f: f.set({"year": y, "loss_ha": ee.Number(f.get("sum")).multiply(PIXEL_HA)}))
        )
        desc = f"landsat_river_{tag}_upazila_{y}"
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
    parser.add_argument("--years", default=None)
    parser.add_argument("--mode", choices=["2yr", "1yr"], default="2yr")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y) for y in args.years.split(",")] if args.years else list(range(1990, 2024))

    if args.dry_run:
        print(f"Landsat river-masked {args.mode}: {len(years)} years, buffer={cfg['gee']['river_buffer_m']}m")
        return

    export_loss(project_id, cfg, years, persistent=(args.mode == "2yr"))


if __name__ == "__main__":
    main()
