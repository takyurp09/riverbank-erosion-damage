#!/usr/bin/env python3
"""Week 7: VIIRS NTL annual mean per upazila (2012–2024).

VCMSLCFG (2014+) is the preferred cloud-free product; VCMCFG fills 2012–2013
where VCMSLCFG has no scenes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gee_utils import load_config, load_upazila_fc

DRIVE_FOLDER = "riverbank_erosion_ntl"
COLLECTIONS = {
    "VCMSLCFG": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
    "VCMCFG": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG",
}


def collection_for_year(year: int) -> str:
    if year <= 2013:
        return COLLECTIONS["VCMCFG"]
    return COLLECTIONS["VCMSLCFG"]


def queue_year(project_id: str, upazilas, year: int) -> None:
    import ee

    ee.Initialize(project=project_id)
    coll_id = collection_for_year(year)
    annual = (
        ee.ImageCollection(coll_id)
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .select("avg_rad")
        .mean()
        .rename("ntl_mean")
    )
    stats = (
        annual.reduceRegions(collection=upazilas, reducer=ee.Reducer.mean(), scale=500, tileScale=4)
        .map(lambda f: f.set({"year": year, "ntl_source": coll_id.split("/")[-1]}))
    )
    desc = f"ntl_viirs_upazila_{year}"
    ee.batch.Export.table.toDrive(
        collection=stats,
        description=desc,
        folder=DRIVE_FOLDER,
        fileNamePrefix=desc,
        fileFormat="CSV",
    ).start()
    print(f"Started: {desc} ({coll_id.split('/')[-1]})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--years", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y) for y in args.years.split(",")] if args.years else list(range(2012, 2025))

    if args.dry_run:
        for y in years:
            print(f"  {y}: {collection_for_year(y).split('/')[-1]}")
        return

    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)

    for y in years:
        queue_year(project_id, upazilas, y)


if __name__ == "__main__":
    main()
