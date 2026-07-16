#!/usr/bin/env python3
"""Phase 6: SSP scenario accounting — project erosion & damage 2025–2050 from ISIMIP discharge."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[2]


def upazila_baselines(panel: pd.DataFrame) -> pd.DataFrame:
    """Historical mean log erosion and damage per ha by upazila (2000–2020)."""
    sub = panel[panel["year"].between(2000, 2020)].copy()
    sub["log_erosion"] = np.log1p(sub["erosion_gross_ha_calibrated"].fillna(0))
    sub["damage_per_ha"] = sub["D_total_asset_usd"] / sub["erosion_gross_ha_calibrated"].replace(0, np.nan)
    base = sub.groupby("upazila_pcode").agg(
        log_erosion_mean=("log_erosion", "mean"),
        damage_per_ha_median=("damage_per_ha", "median"),
        erosion_ha_mean=("erosion_gross_ha_calibrated", "mean"),
    ).reset_index()
    return base


def main() -> None:
    isimip_path = ROOT / "data/processed/panel/isimip_upazila_discharge.parquet"
    if not isimip_path.exists():
        print("Missing isimip_upazila_discharge.parquet — download ISIMIP data and run process_isimip_discharge.py")
        return

    coefs = pd.read_csv(ROOT / "output/tables/driver_regression_coefs.csv")
    beta_dis = coefs.loc[coefs["term"] == "discharge_anomaly_pct", "coef"].iloc[0]

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    baselines = upazila_baselines(panel)
    isimip = pd.read_parquet(isimip_path)

    merged = isimip.merge(baselines, on="upazila_pcode", how="left")
    merged["log_erosion_pred"] = merged["log_erosion_mean"] + beta_dis * merged["discharge_anomaly_pct"].fillna(0)
    merged["erosion_ha_pred"] = np.expm1(merged["log_erosion_pred"]).clip(lower=0)
    merged["damage_usd_pred"] = merged["erosion_ha_pred"] * merged["damage_per_ha_median"].fillna(0)

    # National totals by year × GCM × scenario
    national = (
        merged.groupby(["year", "gcm", "scenario"])
        .agg(
            erosion_ha=("erosion_ha_pred", "sum"),
            damage_usd=("damage_usd_pred", "sum"),
        )
        .reset_index()
    )

    # Ensemble summary: mean and 5th–95th across GCMs per year × scenario
    ensemble = (
        national.groupby(["year", "scenario"])["damage_usd"]
        .agg(
            mean_usd="mean",
            p5_usd=lambda s: np.percentile(s, 5),
            p95_usd=lambda s: np.percentile(s, 95),
            n_gcm="count",
        )
        .reset_index()
    )

    # Compare to historical baseline (2000–2020 national mean)
    hist = panel[panel["year"].between(2000, 2020)]
    hist_damage = hist["D_total_asset_usd"].sum() / hist["year"].nunique()
    hist_erosion = hist["erosion_gross_ha_calibrated"].sum() / hist["year"].nunique()

    summary_rows = []
    for scenario in ensemble["scenario"].unique():
        sub = ensemble[ensemble["scenario"] == scenario]
        mid = sub[sub["year"].between(2045, 2050)]
        summary_rows.append(
            {
                "scenario": scenario,
                "hist_damage_usd_yr": hist_damage,
                "hist_erosion_ha_yr": hist_erosion,
                "proj_damage_usd_yr_2045_2050_mean": mid["mean_usd"].mean(),
                "proj_damage_p5": mid["p5_usd"].mean(),
                "proj_damage_p95": mid["p95_usd"].mean(),
                "pct_change_vs_hist": (mid["mean_usd"].mean() / hist_damage - 1) * 100,
            }
        )

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)
    national.to_csv(out / "ssp_national_by_gcm.csv", index=False)
    ensemble.to_csv(out / "ssp_ensemble_damage_by_year.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(out / "ssp_scenario_summary.csv", index=False)

    print(f"SSP scenario accounting → {out.name}/ssp_*.csv")
    for row in summary_rows:
        print(
            f"  {row['scenario']}: 2045–2050 damage ${row['proj_damage_usd_yr_2045_2050_mean']/1e6:.0f}M/yr "
            f"({row['pct_change_vs_hist']:+.0f}% vs hist ${hist_damage/1e6:.0f}M/yr)"
        )


if __name__ == "__main__":
    main()
