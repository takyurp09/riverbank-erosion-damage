#!/usr/bin/env python3
"""Extract ERA5 monthly precipitation anomaly → upazila panel (centroid sample)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import xarray as xr
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config()
    nc_path = ROOT / cfg["paths"]["processed_climate"] / "cds" / "era5_monthly_precip_bgd.nc"
    if not nc_path.exists():
        print(f"Missing {nc_path.name}")
        return

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["crs"])
    upazila["centroid"] = upazila.geometry.representative_point()

    ds = xr.open_dataset(nc_path)
    da = ds["tp"] * 1000  # metres of water → mm

    rows = []
    for _, u in upazila.iterrows():
        lon, lat = u["centroid"].x, u["centroid"].y
        ts = da.sel(latitude=lat, longitude=lon, method="nearest")
        for t, val in zip(ts["valid_time"].values, ts.values):
            t = pd.Timestamp(t)
            rows.append(
                {
                    "upazila_pcode": u["adm3_pcode"],
                    "year": t.year,
                    "month": t.month,
                    "era5_precip_mm": float(val),
                }
            )

    monthly = pd.DataFrame(rows)
    annual = monthly.groupby(["upazila_pcode", "year"])["era5_precip_mm"].sum().reset_index()
    baseline = (
        annual[annual["year"].between(1990, 2020)]
        .groupby("upazila_pcode")["era5_precip_mm"]
        .mean()
        .rename("era5_precip_baseline_mm")
    )
    annual = annual.merge(baseline, on="upazila_pcode", how="left")
    annual["era5_precip_anomaly_pct"] = (
        (annual["era5_precip_mm"] - annual["era5_precip_baseline_mm"]) / annual["era5_precip_baseline_mm"] * 100
    )

    out = ROOT / cfg["paths"]["processed_climate"] / "era5_precip_upazila_year.parquet"
    annual.to_parquet(out, index=False)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    panel = panel.drop(columns=["era5_precip_mm", "era5_precip_anomaly_pct"], errors="ignore")
    panel = panel.merge(
        annual[["upazila_pcode", "year", "era5_precip_mm", "era5_precip_anomaly_pct"]],
        on=["upazila_pcode", "year"],
        how="left",
    )
    panel.to_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet", index=False)
    print(f"ERA5 annual precip → {len(annual)} upazila-years, merged to panel")


if __name__ == "__main__":
    main()
