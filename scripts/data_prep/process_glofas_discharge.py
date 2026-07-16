#!/usr/bin/env python3
"""Extract GloFAS monsoon discharge at river-reach centroids → discharge anomaly panel."""

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
    nc_path = ROOT / cfg["paths"]["processed_climate"] / "cds" / "glofas_discharge_monsoon_bgd.nc"
    if not nc_path.exists():
        print(f"Missing {nc_path.name} — run week4_cds_download.py --glofas-only first")
        return

    assign = pd.read_csv(ROOT / cfg["paths"]["processed_hydro"] / "upazila_river_reach.csv")
    reach_ids = assign["main_river_flag"].dropna().unique().astype(int)

    rivers = gpd.read_file(ROOT / cfg["paths"]["processed_hydro"] / "hydrorivers_bgd.gpkg")
    rivers = rivers[rivers["HYRIV_ID"].isin(reach_ids)].copy()
    study_crs = cfg["project"]["study_crs"]
    rivers = rivers.to_crs(study_crs)
    rivers["centroid"] = rivers.geometry.centroid.to_crs(cfg["project"]["crs"])

    ds = xr.open_dataset(nc_path)
    var = "dis24" if "dis24" in ds.data_vars else next(
        (v for v in ds.data_vars if "dis" in v.lower()), list(ds.data_vars)[0]
    )
    da = ds[var]
    time_dim = "valid_time" if "valid_time" in da.dims else "time"

    rows = []
    for _, reach in rivers.iterrows():
        lon, lat = reach["centroid"].x, reach["centroid"].y
        ts = da.sel(latitude=lat, longitude=lon, method="nearest")
        years = pd.to_datetime(ts[time_dim].values).year
        df_ts = pd.DataFrame({"year": years, "discharge": ts.values})
        annual = df_ts.groupby("year")["discharge"].mean()
        for year, val in annual.items():
            rows.append(
                {
                    "river_reach_id": reach["HYRIV_ID"],
                    "year": int(year),
                    "discharge_cms": float(val),
                }
            )

    reach_year = pd.DataFrame(rows)
    baseline = (
        reach_year[reach_year["year"].between(1990, 2020)]
        .groupby("river_reach_id")["discharge_cms"]
        .mean()
        .rename("discharge_baseline_cms")
    )
    reach_year = reach_year.merge(baseline, on="river_reach_id", how="left")
    reach_year["discharge_anomaly_pct"] = (
        (reach_year["discharge_cms"] - reach_year["discharge_baseline_cms"])
        / reach_year["discharge_baseline_cms"]
        * 100
    )

    out_dir = ROOT / cfg["paths"]["processed_hydro"]
    reach_year.to_parquet(out_dir / "glofas_reach_discharge_year.parquet", index=False)

    # Merge to upazila panel via reach assignment
    assign = pd.read_csv(out_dir / "upazila_river_reach.csv")
    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    reach_cols = reach_year.rename(columns={"river_reach_id": "main_river_flag"})
    merged = assign.merge(
        reach_cols[["main_river_flag", "year", "discharge_cms", "discharge_anomaly_pct"]],
        on="main_river_flag",
        how="left",
    )
    upa_dis = merged.groupby(["upazila_pcode", "year"]).first().reset_index()
    panel = panel.drop(columns=["discharge_cms", "discharge_anomaly_pct", "discharge_source"], errors="ignore")
    panel = panel.merge(
        upa_dis[["upazila_pcode", "year", "discharge_cms", "discharge_anomaly_pct"]],
        on=["upazila_pcode", "year"],
        how="left",
    )
    panel["discharge_source"] = "glofas"
    panel.to_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet", index=False)
    print(f"GloFAS reach-years: {len(reach_year)}, merged to panel")


if __name__ == "__main__":
    main()
