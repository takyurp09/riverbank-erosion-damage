#!/usr/bin/env python3
"""Robustness checks per project_plan Section 7."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import yaml

ROOT = Path(__file__).resolve().parents[2]

RIVER_SYSTEMS = {
    "Jamuna": ["Sirajganj", "Gaibandha", "Kurigram", "Jamalpur", "Bogura"],
    "Padma": ["Manikganj", "Rajbari", "Shariatpur", "Madaripur", "Faridpur"],
    "Meghna": ["Chandpur", "Bhola", "Lakshmipur", "Noakhali", "Barishal"],
}


def driver_r2(panel: pd.DataFrame, year_start: int, year_end: int) -> dict:
    df = panel[
        panel["year"].between(year_start, year_end)
        & panel["erosion_gross_ha_calibrated"].notna()
        & (panel["erosion_gross_ha_calibrated"] > 0)
    ].copy()
    if len(df) < 100:
        return {"n_obs": len(df), "r2": np.nan}
    df["log_erosion"] = np.log1p(df["erosion_gross_ha_calibrated"])
    for col in ("discharge_anomaly_pct", "precip_anomaly_pct", "spei3_mean"):
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0)
    model = smf.ols(
        "log_erosion ~ discharge_anomaly_pct + precip_anomaly_pct + spei3_mean + C(upazila_pcode)",
        data=df,
    ).fit(cov_type="cluster", cov_kwds={"groups": df["district_pcode"]})
    return {"n_obs": len(df), "r2": model.rsquared}


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    reach = pd.read_csv(ROOT / cfg["paths"]["processed_hydro"] / "upazila_river_reach.csv")
    dist = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_district.gpkg")
    dmap = dist.set_index("adm2_pcode")["adm2_name"].to_dict()
    panel["district_name"] = panel["district_pcode"].map(dmap)

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)

    # 1yr vs 2yr national totals
    nat = panel.groupby("year").agg(
        erosion_1yr_river=("erosion_gross_ha_1yr_river", "sum"),
        erosion_2yr_river=("erosion_gross_ha_2yr_river", "sum"),
        erosion_2yr_calibrated=("erosion_gross_ha_calibrated", "sum"),
    ).reset_index()
    nat.to_csv(out / "robustness_erosion_persistence.csv", index=False)

    # River system breakdown
    rows = []
    sub = panel[panel["year"].between(2000, 2020)]
    for system, districts in RIVER_SYSTEMS.items():
        mask = sub["district_name"].isin(districts)
        rows.append({
            "river_system": system,
            "mean_erosion_ha_yr_calibrated": sub.loc[mask, "erosion_gross_ha_calibrated"].sum() / 21,
            "mean_damage_usd_yr": sub.loc[mask, "D_total_asset_usd"].sum() / 21,
            "n_districts_matched": sub.loc[mask, "district_name"].nunique(),
        })
    pd.DataFrame(rows).to_csv(out / "river_system_breakdown.csv", index=False)

    # 2000–2024 vs 1990–2024 subsample (national damage)
    period_rows = []
    for label, y0, y1 in [("1990-2024", 1990, 2024), ("2000-2024", 2000, 2024), ("2000-2020", 2000, 2020)]:
        s = panel[panel["year"].between(y0, y1)]
        period_rows.append({
            "period": label,
            "mean_erosion_ha_yr": s.groupby("year")["erosion_gross_ha_calibrated"].sum().mean(),
            "mean_D_total_usd_yr": s.groupby("year")["D_total_asset_usd"].sum().mean(),
            "mean_D_total_npv_usd_yr": s.groupby("year")["D_total_asset_npv_usd"].sum().mean()
            if "D_total_asset_npv_usd" in s.columns
            else np.nan,
        })
    pd.DataFrame(period_rows).to_csv(out / "robustness_period_subsamples.csv", index=False)

    # Driver regression subsamples
    reg_rows = [
        {"sample": k, **driver_r2(panel, *v)}
        for k, v in {
            "1990-2024": (1990, 2024),
            "2000-2024": (2000, 2024),
            "2000-2020": (2000, 2020),
        }.items()
    ]
    pd.DataFrame(reg_rows).to_csv(out / "robustness_driver_regression_subsamples.csv", index=False)

    # Placebo: upazilas with lowest embankment + farthest from main river (proxy non-riverine)
    reach_ids = set(reach["upazila_pcode"].unique())
    panel["river_assigned"] = panel["upazila_pcode"].isin(reach_ids)
    placebo_upa = (
        panel.groupby("upazila_pcode")
        .agg(embankment_km=("embankment_km", "first"), river_assigned=("river_assigned", "first"))
        .reset_index()
    )
    placebo_upa = placebo_upa.sort_values("embankment_km").head(50)
    placebo_ids = set(placebo_upa["upazila_pcode"])
    placebo = panel[panel["upazila_pcode"].isin(placebo_ids) & panel["year"].between(2000, 2020)]
    pd.DataFrame([{
        "n_upazilas": len(placebo_ids),
        "mean_erosion_ha_yr": placebo.groupby("year")["erosion_gross_ha_calibrated"].sum().mean(),
        "mean_damage_usd_yr": placebo.groupby("year")["D_total_asset_usd"].sum().mean(),
    }]).to_csv(out / "robustness_placebo_low_embankment.csv", index=False)

    # D_land method comparison (national 2000-2020)
    if "D_land_npv_usd" in panel.columns:
        s = panel[panel["year"].between(2000, 2020)]
        land_cmp = pd.DataFrame([{
            "D_land_ntl_usd_yr": s.groupby("year")["D_land_ntl_usd"].sum().mean(),
            "D_land_npv_usd_yr": s.groupby("year")["D_land_npv_usd"].sum().mean(),
            "D_land_transfer_usd_yr": s.groupby("year")["D_land_transfer_usd"].sum().mean(),
            "D_total_ntl_usd_yr": s.groupby("year")["D_total_asset_usd"].sum().mean(),
            "D_total_npv_usd_yr": s.groupby("year")["D_total_asset_npv_usd"].sum().mean(),
            "D_total_transfer_usd_yr": s.groupby("year")["D_total_asset_transfer_usd"].sum().mean(),
        }])
        land_cmp.to_csv(out / "robustness_d_land_methods.csv", index=False)

    # Cumulative erosion hotspots (Phase 3)
    cum = (
        panel[panel["year"].between(1990, 2024)]
        .groupby(["upazila_pcode", "upazila_name", "district_name"], as_index=False)
        .agg(
            cumulative_erosion_ha=("erosion_gross_ha_calibrated", "sum"),
            cumulative_damage_usd=("D_total_asset_usd", "sum"),
        )
        .sort_values("cumulative_erosion_ha", ascending=False)
    )
    cum.head(50).to_csv(out / "cumulative_erosion_hotspots_top50.csv", index=False)

    # Sentinel-2 vs Landsat (2017–2020 overlap)
    if "erosion_gross_ha_2yr_s2_river" in panel.columns:
        s2 = panel[panel["year"].between(2017, 2020)]
        cmp = s2.groupby("year").agg(
            landsat_2yr=("erosion_gross_ha_2yr_river_landsat", "sum"),
            s2_2yr=("erosion_gross_ha_2yr_s2_river", "sum"),
            jrc_2yr_cal=("erosion_gross_ha_calibrated", "sum"),
        ).reset_index()
        cmp["s2_vs_landsat_ratio"] = cmp["s2_2yr"] / cmp["landsat_2yr"].replace(0, np.nan)
        cmp.to_csv(out / "robustness_sentinel2_landsat.csv", index=False)

    # Gross vs net erosion (when accretion processed)
    if "erosion_net_ha_2yr" in panel.columns:
        sub = panel.groupby("year").agg(
            gross_2yr=("erosion_gross_ha_2yr_river", "sum"),
            accretion_2yr=("accretion_gross_ha_2yr", "sum"),
            net_2yr=("erosion_net_ha_2yr", "sum"),
        ).reset_index()
        sub.to_csv(out / "robustness_gross_vs_net_erosion.csv", index=False)

    print(f"Robustness tables → {out.name}/ ({len(list(out.glob('robustness*.csv')))} files)")


if __name__ == "__main__":
    main()
