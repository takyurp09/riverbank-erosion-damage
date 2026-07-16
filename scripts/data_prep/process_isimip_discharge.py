#!/usr/bin/env python3
"""Extract ISIMIP3b daily discharge at river-reach centroids → reach-year panel by GCM × scenario."""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import xarray as xr
import yaml

ROOT = Path(__file__).resolve().parents[2]

MONSOON_MONTHS = {6, 7, 8, 9, 10}


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def parse_file_meta(path: Path) -> tuple[str, str]:
    """Infer GCM and scenario from our names or CWatM ISIMIP filenames."""
    stem = path.stem.lower()
    gcm_match = re.search(
        r"(gfdl-esm4|ipsl-cm6a-lr|mpi-esm1-2-hr|mri-esm2-0|ukesm1-0-ll)", stem
    )
    scen_match = re.search(r"(ssp126|ssp585|historical)", stem)
    if gcm_match and scen_match:
        return gcm_match.group(1), scen_match.group(1)
    raise ValueError(f"Cannot parse GCM/scenario from {path.name}")


def discharge_var(ds: xr.Dataset) -> str:
    for name in ("dis", "dis24", "discharge"):
        if name in ds.data_vars:
            return name
    for name in ds.data_vars:
        if "dis" in name.lower():
            return name
    return list(ds.data_vars)[0]


def time_dim(da: xr.DataArray) -> str:
    for dim in ("time", "valid_time"):
        if dim in da.dims:
            return dim
    raise ValueError("No time dimension found")


def lat_lon_names(ds: xr.Dataset) -> tuple[str, str]:
    lat = next((d for d in ("lat", "latitude", "y") if d in ds.coords or d in ds.dims), "lat")
    lon = next((d for d in ("lon", "longitude", "x") if d in ds.coords or d in ds.dims), "lon")
    return lat, lon


def extract_reach_series(
    nc_path: Path, rivers: gpd.GeoDataFrame, gcm: str, scenario: str
) -> pd.DataFrame:
    ds = xr.open_dataset(nc_path)
    var = discharge_var(ds)
    da = ds[var]
    tdim = time_dim(da)
    lat_name, lon_name = lat_lon_names(ds)

    times = pd.to_datetime(ds[tdim].values)
    monsoon_mask = times.month.isin(MONSOON_MONTHS)

    rows = []
    for _, reach in rivers.iterrows():
        lon, lat = reach["centroid"].x, reach["centroid"].y
        ts = da.sel({lon_name: lon, lat_name: lat}, method="nearest")
        vals = ts.values[monsoon_mask]
        yrs = times.year[monsoon_mask]
        df_ts = pd.DataFrame({"year": yrs, "discharge": vals})
        annual = df_ts.groupby("year")["discharge"].mean()
        for year, val in annual.items():
            rows.append(
                {
                    "river_reach_id": int(reach["HYRIV_ID"]),
                    "year": int(year),
                    "gcm": gcm,
                    "scenario": scenario,
                    "discharge_cms": float(val),
                }
            )
    ds.close()
    return pd.DataFrame(rows)


def main() -> None:
    cfg = load_config()
    isimip_dir = ROOT / cfg["paths"]["processed_climate"] / "isimip"
    nc_files = sorted(isimip_dir.glob("*.nc"))
    if not nc_files:
        print(f"No ISIMIP NetCDF files in {isimip_dir} — run week5_isimip_download.py checklist first")
        return

    assign = pd.read_csv(ROOT / cfg["paths"]["processed_hydro"] / "upazila_river_reach.csv")
    reach_ids = assign["main_river_flag"].dropna().unique().astype(int)

    rivers = gpd.read_file(ROOT / cfg["paths"]["processed_hydro"] / "hydrorivers_bgd.gpkg")
    rivers = rivers[rivers["HYRIV_ID"].isin(reach_ids)].copy()
    rivers = rivers.to_crs(cfg["project"]["study_crs"])
    rivers["centroid"] = rivers.geometry.centroid.to_crs(cfg["project"]["crs"])

    all_rows = []
    for nc in nc_files:
        try:
            gcm, scenario = parse_file_meta(nc)
        except ValueError as exc:
            print(f"Skipping {nc.name}: {exc}")
            continue
        print(f"Processing {nc.name} ({gcm}, {scenario})…")
        all_rows.append(extract_reach_series(nc, rivers, gcm, scenario))

    if not all_rows:
        print("No ISIMIP files parsed successfully")
        return

    reach_year = pd.concat(all_rows, ignore_index=True)

    # Baseline: 1990–2020 mean per reach × GCM (historical or early scenario years)
    baseline = (
        reach_year[reach_year["year"].between(1990, 2020)]
        .groupby(["river_reach_id", "gcm"])["discharge_cms"]
        .mean()
        .rename("discharge_baseline_cms")
        .reset_index()
    )
    reach_year = reach_year.merge(baseline, on=["river_reach_id", "gcm"], how="left")
    reach_year["discharge_anomaly_pct"] = (
        (reach_year["discharge_cms"] - reach_year["discharge_baseline_cms"])
        / reach_year["discharge_baseline_cms"]
        * 100
    )

    out_hydro = ROOT / cfg["paths"]["processed_hydro"]
    out_path = out_hydro / "isimip_reach_discharge_year.parquet"
    reach_year.to_parquet(out_path, index=False)
    print(f"ISIMIP reach-years: {len(reach_year)} → {out_path.name}")

    # Merge future scenario discharge to panel (2025–2050 only)
    assign = pd.read_csv(out_hydro / "upazila_river_reach.csv")
    future = reach_year[reach_year["year"] >= 2025].copy()
    merged = assign.merge(
        future.rename(columns={"river_reach_id": "main_river_flag"}),
        on="main_river_flag",
        how="inner",
    )
    upa_dis = merged.groupby(["upazila_pcode", "year", "gcm", "scenario"]).first().reset_index()

    scenario_dir = ROOT / "data/processed/panel"
    upa_dis.to_parquet(scenario_dir / "isimip_upazila_discharge.parquet", index=False)
    print(f"Upazila-level ISIMIP discharge → panel/isimip_upazila_discharge.parquet ({len(upa_dis)} rows)")


if __name__ == "__main__":
    main()
