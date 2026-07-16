#!/usr/bin/env python3
"""CHIRPS monthly precip → annual upazila total via GEE."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[2]
DRIVE_FOLDER = "riverbank_erosion_chirps"


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def load_upazila_fc(cfg: dict):
    import ee

    gdf = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    gdf = gdf[["adm3_pcode", "adm3_name", "adm2_pcode", "geometry"]].to_crs(cfg["project"]["crs"])
    gdf["geometry"] = gdf.geometry.simplify(0.001, preserve_topology=True)
    return ee.FeatureCollection(gdf.__geo_interface__)


def queue_exports(project_id: str, cfg: dict, years: list[int]) -> None:
    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")

    for y in years:
        annual_mm = (
            chirps.filter(ee.Filter.calendarRange(y, y, "year"))
            .select("precipitation")
            .sum()
            .rename("precip_mm")
        )
        stats = (
            annual_mm.reduceRegions(
                collection=upazilas,
                reducer=ee.Reducer.mean(),
                scale=5560,
                tileScale=4,
            )
            .map(lambda f: f.set("year", y))
        )
        desc = f"chirps_precip_upazila_{y}"
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y) for y in args.years.split(",")] if args.years else list(range(1990, 2025))

    if args.dry_run:
        print(f"CHIRPS exports: {len(years)} years")
        return

    queue_exports(project_id, cfg, years)


if __name__ == "__main__":
    main()
