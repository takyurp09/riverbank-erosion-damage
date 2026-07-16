#!/usr/bin/env python3
"""Face-validity check: known erosion hotspot districts vs JRC panel."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]

HOTSPOT_DISTRICTS = [
    "Sirajganj", "Gaibandha", "Kurigram", "Jamalpur", "Bogura",
    "Manikganj", "Rajbari", "Shariatpur", "Chandpur", "Bhola", "Lakshmipur",
]


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")

    erosion_col = "erosion_gross_ha_calibrated"
    if erosion_col not in panel.columns:
        erosion_col = "erosion_gross_ha_2yr_primary"
    if erosion_col not in panel.columns:
        erosion_col = "erosion_gross_ha_2yr_river"
    if erosion_col not in panel.columns:
        erosion_col = "erosion_gross_ha_2yr"

    yearly = (
        panel.groupby(["district_pcode", "year"])[erosion_col]
        .sum()
        .reset_index()
    )

    # Load district names
    import geopandas as gpd
    dist = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_district.gpkg")
    dist_names = dist[["adm2_pcode", "adm2_name"]].rename(
        columns={"adm2_pcode": "district_pcode", "adm2_name": "district_name"}
    )
    yearly = yearly.merge(dist_names, on="district_pcode", how="left")

    mean_erosion = yearly.groupby("district_name")[erosion_col].mean().sort_values(ascending=False)
    national_mean = yearly[erosion_col].mean()

    out_dir = ROOT / "output/tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = []
    for d in HOTSPOT_DISTRICTS:
        val = mean_erosion.get(d, float("nan"))
        report.append(
            {
                "district": d,
                "mean_annual_erosion_ha_2yr": val,
                "erosion_series": erosion_col,
                "above_national_mean": val > national_mean if pd.notna(val) else None,
                "national_rank": mean_erosion.index.get_loc(d) + 1 if d in mean_erosion.index else None,
            }
        )

    report_df = pd.DataFrame(report)
    report_df.to_csv(out_dir / "face_validity_hotspots.csv", index=False)
    mean_erosion.head(20).to_csv(out_dir / "top20_districts_erosion.csv")

    n_pass = report_df["above_national_mean"].sum()
    print(f"Hotspot districts above national mean: {n_pass}/{len(HOTSPOT_DISTRICTS)}")
    print(f"Saved: output/tables/face_validity_hotspots.csv")


if __name__ == "__main__":
    main()
