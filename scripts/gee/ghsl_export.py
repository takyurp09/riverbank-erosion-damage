#!/usr/bin/env python3
"""Week 4: GHSL population sum per upazila (1975–2030, 5-yr steps)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gee_utils import load_config, load_upazila_fc

DRIVE_FOLDER = "riverbank_erosion_ghsl"
COLLECTION = "JRC/GHSL/P2023A/GHS_POP"
DEFAULT_YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--years", default=None, help="Comma-separated, e.g. 1990,2000,2020")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y) for y in args.years.split(",")] if args.years else DEFAULT_YEARS

    if args.dry_run:
        print(f"GHSL exports → {DRIVE_FOLDER}: {years}")
        return

    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)
    ghsl = ee.ImageCollection(COLLECTION)

    for y in years:
        pop = (
            ghsl.filter(ee.Filter.calendarRange(y, y, "year"))
            .first()
            .select("population_count")
            .rename("ghsl_pop")
        )
        stats = (
            pop.reduceRegions(collection=upazilas, reducer=ee.Reducer.sum(), scale=100, tileScale=4)
            .map(lambda f: f.set("year", y))
        )
        desc = f"ghsl_pop_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")


if __name__ == "__main__":
    main()
