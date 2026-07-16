#!/usr/bin/env python3
"""WorldPop Global1: download BGD rasters, zonal pop sum per upazila, delete raw."""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml
from rasterstats import zonal_stats

ROOT = Path(__file__).resolve().parents[2]
WORLDPOP_URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020/{year}/BGD/bgd_ppp_{year}.tif"


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def download_year(year: int, dest: Path) -> None:
    url = WORLDPOP_URL.format(year=year)
    if dest.exists() and dest.stat().st_size > 1000:
        return
    print(f"  Downloading {year}...", flush=True)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)


def main() -> None:
    cfg = load_config()
    years = list(range(2000, 2021))
    raw_dir = ROOT / cfg["paths"]["raw"] / "worldpop"
    out_dir = ROOT / "data/processed/population"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["crs"])
    shapes = upazila.__geo_interface__["features"]

    rows = []
    for year in years:
        tif = raw_dir / f"bgd_ppp_{year}.tif"
        download_year(year, tif)

        stats = zonal_stats(
            shapes,
            str(tif),
            stats="sum",
            nodata=-99999,
            geojson_out=True,
        )
        for feat, stat in zip(shapes, stats):
            props = feat["properties"]
            pop = stat["properties"].get("sum") or 0
            area_km2 = props.get("area_sqkm") or 0
            rows.append(
                {
                    "upazila_pcode": props["adm3_pcode"],
                    "year": year,
                    "pop_total": pop,
                    "pop_density_km2": pop / area_km2 if area_km2 else None,
                }
            )
        tif.unlink(missing_ok=True)
        print(f"  {year}: zonal stats done, raw deleted", flush=True)

    panel = pd.DataFrame(rows)
    panel.to_parquet(out_dir / "worldpop_upazila_year.parquet", index=False)
    panel.to_csv(out_dir / "worldpop_upazila_year.csv", index=False)

    if raw_dir.exists() and not any(raw_dir.iterdir()):
        raw_dir.rmdir()

    print(f"Saved {len(panel)} rows → data/processed/population/")


if __name__ == "__main__":
    main()
