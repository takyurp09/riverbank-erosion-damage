#!/usr/bin/env python3
"""Global Mangrove Watch v3 mangrove fraction per upazila (GMW_V3 + union baseline)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gee_utils import load_config, load_upazila_fc

DRIVE_FOLDER = "riverbank_erosion_mangrove"
PIXEL_HA_30 = 30 * 30 / 10_000


def available_gmw_years(gmw) -> list[int]:
    """Years present in GMW_V3 (system:index gmw_v3_YYYY). No 2000 layer exists."""
    indexes = gmw.aggregate_array("system:index").getInfo() or []
    return sorted(int(i.rsplit("_", 1)[-1]) for i in indexes if i.startswith("gmw_v3_"))


def gmw_image_for_year(gmw, year: int):
    import ee

    idx = f"gmw_v3_{year}"
    # b1 is 0/1 extent; use float mean (not binary gt) for true area fraction
    return ee.Image(gmw.filter(ee.Filter.eq("system:index", idx)).first()).select("b1").unmask(0)


def queue_exports(project_id: str, cfg: dict, years: list[int], *, include_union: bool = True) -> None:
    import ee

    ee.Initialize(project=project_id)
    upazilas = load_upazila_fc(cfg)
    scale = cfg["gee"]["export_scale_m"]
    gmw = ee.ImageCollection("projects/sat-io/open-datasets/GMW/extent/GMW_V3")
    valid = set(available_gmw_years(gmw))

    missing = [y for y in years if y not in valid]
    if missing:
        nearest = {y: min(valid, key=lambda v: abs(v - y)) for y in missing}
        print(
            "Skipping years not in GMW_V3:",
            ", ".join(f"{y} (nearest: {nearest[y]})" for y in missing),
        )
    years = [y for y in years if y in valid]
    if not years:
        raise SystemExit("No valid GMW years to export. Available: " + ", ".join(map(str, sorted(valid))))

    # Static union baseline (max extent)
    if include_union:
        union = ee.Image("projects/sat-io/open-datasets/GMW/union/gmw_v3_mng_union").select("b1").unmask(0)
        union_stats = (
            union.rename("mangrove")
            .reduceRegions(collection=upazilas, reducer=ee.Reducer.mean(), scale=scale, tileScale=4)
            .map(lambda f: f.set({"year": 2020, "mangrove_frac": f.get("mean"), "source": "gmw_union"}))
        )
        ee.batch.Export.table.toDrive(
            collection=union_stats,
            description="gmw_union_frac_upazila",
            folder=DRIVE_FOLDER,
            fileNamePrefix="gmw_union_frac_upazila",
            fileFormat="CSV",
        ).start()
        print("Started: gmw_union_frac_upazila")

    for y in years:
        img = gmw_image_for_year(gmw, y)
        stats = (
            img.rename("mangrove")
            .reduceRegions(collection=upazilas, reducer=ee.Reducer.mean(), scale=scale, tileScale=8)
            .map(lambda f: f.set({"year": y, "mangrove_frac": f.get("mean"), "source": "gmw_v3"}))
        )
        desc = f"gmw_frac_upazila_{y}"
        ee.batch.Export.table.toDrive(
            collection=stats,
            description=desc,
            folder=DRIVE_FOLDER,
            fileNamePrefix=desc,
            fileFormat="CSV",
        ).start()
        print(f"Started: {desc}")

    print(f"\nQueued GMW exports → Drive/{DRIVE_FOLDER}/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--years", default="1996,2010,2020",
                        help="Comma-separated years (must exist in GMW_V3; 2000 is not available)")
    parser.add_argument("--list-years", action="store_true",
                        help="Print available GMW_V3 years and exit")
    parser.add_argument("--extent-only", action="store_true",
                        help="Skip union baseline export (use when re-queuing failed years)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    project_id = args.project or cfg["gee"]["project_id"]
    years = [int(y.strip()) for y in args.years.split(",")]

    if args.dry_run:
        import ee
        ee.Initialize(project=project_id)
        gmw = ee.ImageCollection("projects/sat-io/open-datasets/GMW/extent/GMW_V3")
        avail = available_gmw_years(gmw)
        print(f"GMW_V3 available years: {avail}")
        print(f"Requested export years: {years}")
        return

    if args.list_years:
        import ee
        ee.Initialize(project=project_id)
        gmw = ee.ImageCollection("projects/sat-io/open-datasets/GMW/extent/GMW_V3")
        print("GMW_V3 years:", ", ".join(map(str, available_gmw_years(gmw))))
        return

    queue_exports(project_id, cfg, years, include_union=not args.extent_only)


if __name__ == "__main__":
    main()
