#!/usr/bin/env python3
"""Extend river erosion through erosion_years_end and apply coastal-district mask fallback."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]

# Lower Meghna / coastal islands — river 5 km buffer misses channel-adjacent erosion
COASTAL_DISTRICTS = [
    "Bhola",
    "Lakshmipur",
    "Chandpur",
    "Noakhali",
    "Feni",
    "Patuakhali",
    "Barguna",
    "Barishal",
    "Pirojpur",
    "Jhalokati",
]

EROSION_COLS = [
    "erosion_gross_ha_1yr_river",
    "erosion_gross_ha_2yr_river",
    "erosion_source_extended",
]


def erosion_years_end(cfg: dict) -> int:
    return int(cfg["gee"].get("erosion_years_end", cfg["gee"]["years_end"]))


def apply_coastal_and_extension(panel: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    panel = panel.copy()
    y_end = erosion_years_end(cfg)
    dist = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_district.gpkg")
    dmap = dist.set_index("adm2_pcode")["adm2_name"].to_dict()
    if "district_name" not in panel.columns:
        panel["district_name"] = panel["district_pcode"].map(dmap)

    coastal = panel["district_name"].isin(COASTAL_DISTRICTS)

    # Coastal fallback: use Landsat river, then unmasked JRC/Landsat when river-masked JRC is zero
    river = panel["erosion_gross_ha_2yr_river"].fillna(0)
    landsat_r = panel.get("erosion_gross_ha_2yr_river_landsat", pd.Series(0, index=panel.index)).fillna(0)
    jrc_all = panel.get("erosion_gross_ha_2yr", pd.Series(0, index=panel.index)).fillna(0)
    landsat_all = panel.get("erosion_gross_ha_2yr_landsat", pd.Series(0, index=panel.index)).fillna(0)

    fallback = np.where(landsat_r > 0, landsat_r, np.where(jrc_all > 0, jrc_all, landsat_all))
    panel.loc[coastal & (river == 0), "erosion_gross_ha_2yr_river"] = fallback[coastal & (river == 0)]
    panel["erosion_coastal_fallback"] = coastal & (river == 0) & (panel["erosion_gross_ha_2yr_river"] > 0)

    # Extend 2021–erosion_years_end from Landsat river, then S2 where Landsat is zero
    s2 = panel.get("erosion_gross_ha_2yr_s2_river", pd.Series(np.nan, index=panel.index))
    for y in range(2021, y_end + 1):
        mask = panel["year"] == y
        if not mask.any():
            continue
        fill = landsat_r[mask].where(landsat_r[mask] > 0, s2[mask])
        panel.loc[mask, "erosion_gross_ha_2yr_river"] = fill.values
        panel.loc[mask, "erosion_source_extended"] = np.where(
            landsat_r[mask] > 0,
            "landsat_river",
            np.where(s2[mask].fillna(0) > 0, "s2_river", "landsat_river"),
        )

    # Recompute 1yr river loss from 2yr where missing (approximate: 2yr value at year t)
    if "erosion_gross_ha_1yr_river" in panel.columns:
        gap = panel["erosion_gross_ha_1yr_river"].fillna(0) == 0
        panel.loc[gap, "erosion_gross_ha_1yr_river"] = panel.loc[gap, "erosion_gross_ha_2yr_river"]

    # No Landsat/S2/JRC loss after erosion_years_end — leave NaN, not zero
    after = panel["year"] > y_end
    for col in EROSION_COLS:
        if col in panel.columns:
            panel.loc[after, col] = np.nan

    return panel


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    y_end = erosion_years_end(cfg)
    panel_path = ROOT / "data/processed/panel/panel_upazila_year.parquet"
    panel = pd.read_parquet(panel_path)
    panel = apply_coastal_and_extension(panel, cfg)
    panel.to_parquet(panel_path, index=False)
    panel.to_csv(ROOT / "data/processed/panel/panel_upazila_year.csv", index=False)

    coastal_n = panel["erosion_coastal_fallback"].sum() if "erosion_coastal_fallback" in panel.columns else 0
    ext = panel[panel["year"].between(2021, y_end)]["erosion_gross_ha_2yr_river"].sum()
    print(f"Coastal fallback cells filled: {coastal_n}")
    print(f"2021–{y_end} river erosion total (ha): {ext:,.0f}")
    print(f"Erosion series ends at {y_end} (Landsat river + S2); no 2024 erosion layer")


if __name__ == "__main__":
    main()
