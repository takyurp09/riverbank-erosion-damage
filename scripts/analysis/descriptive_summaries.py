#!/usr/bin/env python3
"""Phase 3: descriptive national summaries — erosion and damage time series."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    damage = pd.read_parquet(ROOT / "data/processed/panel/damage_upazila_year.parquet")
    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)

    erosion_col = "erosion_gross_ha_calibrated"
    nat = panel.groupby("year").agg(
        erosion_ha_calibrated=(erosion_col, "sum"),
        erosion_ha_raw=("erosion_gross_ha_2yr_river", "sum"),
    ).reset_index()

    if "persons_eroded" in panel.columns:
        pop = panel.groupby("year")["persons_eroded"].sum().rename("persons_eroded")
        nat = nat.merge(pop, on="year", how="left")

    dmg = damage.groupby("year").agg(
        D_total_asset_usd=("D_total_asset_usd", "sum"),
        D_struct_usd=("D_struct_usd", "sum"),
        D_displace_usd=("D_displace_usd", "sum"),
        D_ecosys_usd=("D_ecosys_usd", "sum"),
        D_land_ntl_usd=("D_land_ntl_usd", "sum"),
        D_ag_flow_usd=("D_ag_flow_usd", "sum"),
    ).reset_index()

    summary = nat.merge(dmg, on="year", how="outer")
    summary.to_csv(out / "national_erosion_damage_timeseries.csv", index=False)

    top = (
        panel[panel["year"].between(2000, 2020)]
        .groupby(["upazila_pcode", "upazila_name", "district_pcode"])[erosion_col]
        .mean()
        .sort_values(ascending=False)
        .head(25)
        .reset_index()
    )
    top.to_csv(out / "top25_upazilas_erosion_calibrated.csv", index=False)

    print(f"National time series → {out.name}/national_erosion_damage_timeseries.csv")
    print(f"Top upazilas → {out.name}/top25_upazilas_erosion_calibrated.csv")


if __name__ == "__main__":
    main()
