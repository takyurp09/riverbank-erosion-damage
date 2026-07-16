#!/usr/bin/env python3
"""Assign each upazila to a HydroRIVERS reach (river_reach merge key)."""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config()
    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    rivers = gpd.read_file(ROOT / cfg["paths"]["processed_hydro"] / "hydrorivers_bgd.gpkg")

    upazila = upazila.to_crs(cfg["project"]["study_crs"])
    rivers = rivers.to_crs(cfg["project"]["study_crs"])

    # Major rivers only — catchment >= 1000 km² equivalent via discharge proxy
    if "DIS_AV_CMS" in rivers.columns:
        rivers = rivers[rivers["DIS_AV_CMS"] >= 10].copy()

    up_cent = upazila.copy()
    up_cent["geometry"] = upazila.geometry.representative_point()

    nearest = gpd.sjoin_nearest(
        up_cent[["adm3_pcode", "adm3_name", "adm2_pcode", "geometry"]],
        rivers[["HYRIV_ID", "DIS_AV_CMS", "MAIN_RIV", "geometry"]],
        how="left",
        distance_col="dist_m",
    )

    # Prefer intersecting reaches where upazila touches a river
    intersect = gpd.overlay(upazila[["adm3_pcode", "geometry"]], rivers[["HYRIV_ID", "DIS_AV_CMS", "geometry"]], how="intersection")
    if len(intersect) > 0:
        intersect["ix_len"] = intersect.geometry.length
        best_ix = (
            intersect.sort_values(["adm3_pcode", "DIS_AV_CMS", "ix_len"], ascending=[True, False, False])
            .drop_duplicates("adm3_pcode")
            .set_index("adm3_pcode")["HYRIV_ID"]
        )
        nearest = nearest.set_index("adm3_pcode")
        nearest.loc[best_ix.index, "HYRIV_ID"] = best_ix
        nearest = nearest.reset_index()

    out = nearest.rename(
        columns={
            "adm3_pcode": "upazila_pcode",
            "adm3_name": "upazila_name",
            "adm2_pcode": "district_pcode",
            "HYRIV_ID": "river_reach_id",
            "DIS_AV_CMS": "reach_discharge_cms",
            "MAIN_RIV": "main_river_flag",
            "dist_m": "dist_to_reach_m",
        }
    )[["upazila_pcode", "upazila_name", "district_pcode", "river_reach_id", "reach_discharge_cms", "main_river_flag", "dist_to_reach_m"]]

    out = out.sort_values("reach_discharge_cms", ascending=False).drop_duplicates("upazila_pcode", keep="first")

    out_dir = ROOT / "data/processed/hydrology"
    out_path = out_dir / "upazila_river_reach.csv"
    out.to_csv(out_path, index=False)

    n_assigned = out["river_reach_id"].notna().sum()
    print(f"Assigned {n_assigned}/{len(out)} upazilas to river reaches")
    print(f"Saved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
