#!/usr/bin/env python3
"""Week 4–5: ERA5 precip + GloFAS discharge via Copernicus CDS (requires ~/.cdsapirc)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def cds_client(url: str = "https://cds.climate.copernicus.eu/api"):
    import cdsapi

    return cdsapi.Client(url=url)


def download_era5_monthly(cfg: dict, out_dir: Path) -> Path:
    out = out_dir / "era5_monthly_precip_bgd.nc"
    if out.exists():
        print(f"ERA5 exists: {out.name}")
        return out

    bb = cfg["bbox"]
    client = cds_client()
    client.retrieve(
        "reanalysis-era5-single-levels-monthly-means",
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": "total_precipitation",
            "year": [str(y) for y in range(1990, 2025)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": "00:00",
            "area": [bb["north"], bb["west"], bb["south"], bb["east"]],
            "format": "netcdf",
        },
        str(out),
    )
    print(f"Downloaded ERA5 → {out.name}")
    return out


def download_glofas_monsoon(cfg: dict, out_dir: Path) -> Path:
    """Monsoon daily discharge (Jun–Oct) via EWDS — downloaded year-by-year to avoid quota limits."""
    out = out_dir / "glofas_discharge_monsoon_bgd.nc"
    if out.exists():
        print(f"GloFAS exists: {out.name}")
        return out

    import xarray as xr

    bb = cfg["bbox"]
    staging = out_dir / "glofas_staging"
    staging.mkdir(parents=True, exist_ok=True)
    client = cds_client(url="https://ewds.climate.copernicus.eu/api")
    years = list(range(1990, 2025))
    parts = []

    for y in years:
        part = staging / f"glofas_{y}.nc"
        if part.exists():
            print(f"  skip {y} (cached)")
            parts.append(part)
            continue
        print(f"  downloading GloFAS {y}...")
        client.retrieve(
            "cems-glofas-historical",
            {
                "variable": "river_discharge_in_the_last_24_hours",
                "hydrological_model": "lisflood",
                "product_type": "consolidated",
                "system_version": "version_4_0",
                "hyear": [str(y)],
                "hmonth": ["06", "07", "08", "09", "10"],
                "hday": [f"{d:02d}" for d in range(1, 32)],
                "area": [bb["north"], bb["west"], bb["south"], bb["east"]],
                "data_format": "netcdf",
                "download_format": "unarchived",
            },
            str(part),
        )
        parts.append(part)

    print("Merging GloFAS yearly files...")
    ds = xr.open_mfdataset([str(p) for p in parts], combine="by_coords")
    ds.to_netcdf(out)
    ds.close()
    for p in parts:
        p.unlink(missing_ok=True)
    staging.rmdir()
    print(f"Downloaded GloFAS → {out.name}")
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--era5-only", action="store_true")
    parser.add_argument("--glofas-only", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    out_dir = ROOT / cfg["paths"]["processed_climate"] / "cds"
    out_dir.mkdir(parents=True, exist_ok=True)

    cds_rc = Path.home() / ".cdsapirc"
    if not cds_rc.exists():
        print(
            "No ~/.cdsapirc found. Create CDS API credentials at "
            "https://cds.climate.copernicus.eu/ then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.glofas_only:
        download_era5_monthly(cfg, out_dir)
    if not args.era5_only:
        download_glofas_monsoon(cfg, out_dir)


if __name__ == "__main__":
    main()
