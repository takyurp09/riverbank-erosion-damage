#!/usr/bin/env python3
"""JRC GSW land-loss exports masked to river buffer → upazila zonal CSV on GEE."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gee_utils import load_config, load_upazila_fc, erosion_zone_geometry

ROOT = Path(__file__).resolve().parents[2]
DRIVE_FOLDER = "riverbank_erosion_jrc_river"
PIXEL_HA = 30 * 30 / 10_000


def available_jrc_years(yearly) -> list[int]:
    """Calendar years present in JRC/GSW1_4/YearlyHistory."""
    import ee
    from datetime import datetime

    starts = yearly.aggregate_array("system:time_start").getInfo() or []
    return sorted({datetime.utcfromtimestamp(t / 1000).year for t in starts})


def jrc_land_loss_fn(yearly):
    import ee

    def water_class_year(y: int):
        return (
            yearly.filter(ee.Filter.calendarRange(y, y, "year"))
            .first()
            .select("waterClass")
        )

    def annual_land_loss(y: int):
        return water_class_year(y).eq(1).And(water_class_year(y + 1).gt(1)).rename("loss")

    return annual_land_loss


def queue_zonal_exports(project_id: str, cfg: dict, years: list[int]) -> None:
    import ee

    ee.Initialize(project=project_id)
    bb = cfg["bbox"]
    aoi = ee.Geometry.Rectangle([bb["west"], bb["south"], bb["east"], bb["north"]])
    river_zone = erosion_zone_geometry(cfg, aoi)
    yearly = ee.ImageCollection(cfg["gee"]["jrc_collection"])
    valid = set(available_jrc_years(yearly))
    annual_land_loss = jrc_land_loss_fn(yearly)
    upazilas = load_upazila_fc(cfg)
    scale = cfg["gee"]["export_scale_m"]

    # Loss year y requires waterClass for both y and y+1
    missing = [y for y in years if y not in valid or (y + 1) not in valid]
    if missing:
        print(
            "Skipping JRC loss years (need y and y+1 in YearlyHistory):",
            ", ".join(
                f"{y} (max loss year: {max(valid) - 1})" if y == max(valid) else str(y)
                for y in missing
            ),
        )
    years = [y for y in years if y in valid and (y + 1) in valid]
    if not years:
        print(f"No valid JRC loss years. YearlyHistory covers {min(valid)}–{max(valid)}; last loss year = {max(valid) - 1}")
        print("Use Landsat/S2 exports for years after that.")
        return
        loss = annual_land_loss(y).clip(river_zone)
        stats = (
            loss.reduceRegions(collection=upazilas, reducer=ee.Reducer.sum(), scale=scale, tileScale=4)
            .map(
                lambda f: f.set(
                    {
                        "year": y,
                        "loss_pixels": f.get("sum"),
                        "loss_ha": ee.Number(f.get("sum")).multiply(PIXEL_HA),
                    }
                )
            )
        )
        desc = f"jrc_river_loss_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")

    print(f"\nQueued {len(years)} river-masked JRC exports → Drive/{DRIVE_FOLDER}/")


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
        import ee
        ee.Initialize(project=project_id)
        yearly = ee.ImageCollection(cfg["gee"]["jrc_collection"])
        valid = available_jrc_years(yearly)
        print(f"JRC YearlyHistory: {valid[0]}–{valid[-1]} ({len(valid)} images)")
        print(f"Last valid loss year (needs y+1): {valid[-1] - 1}")
        print(f"Requested: {years}")
        ok = [y for y in years if y in valid and (y + 1) in valid]
        print(f"Would export: {ok}")
        return

    if not project_id:
        print("ERROR: set gee.project_id in config/settings.yaml", file=sys.stderr)
        sys.exit(1)

    queue_zonal_exports(project_id, cfg, years)


if __name__ == "__main__":
    main()
