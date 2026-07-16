#!/usr/bin/env python3
"""Phase 2: estimate D_struct, D_displace, D_ecosys, D_land_ntl per upazila-year."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_params() -> dict:
    with open(ROOT / "config" / "damage_params.yaml") as f:
        return yaml.safe_load(f)


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def building_unit_cost(row: pd.Series, params: dict) -> float:
    pwd = params["pwd_usd_per_m2"]
    avg_m2 = row["footprint_m2"] / max(row["n_buildings"], 1)
    pop_d = row.get("pop_density_km2") or 0
    if avg_m2 > params["building_class"]["semi_pucca_max_m2"] or pop_d > params["building_class"]["urban_pop_density_km2"]:
        return pwd["pucca"]
    if avg_m2 > params["building_class"]["kachha_max_m2"]:
        return pwd["semi_pucca"]
    return pwd["kachha"]


def is_mangrove_district(district_name: str, params: dict) -> bool:
    return district_name in params["ecosystem"]["mangrove_districts"]


def main() -> None:
    cfg = load_config()
    params = load_params()

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    erosion_col = "erosion_gross_ha_calibrated" if "erosion_gross_ha_calibrated" in panel.columns else "erosion_gross_ha_2yr_river"

    dist = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_district.gpkg")
    dist_map = dist.set_index("adm2_pcode")["adm2_name"].to_dict()
    panel["district_name"] = panel["district_pcode"].map(dist_map)

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    area_ha = upazila.set_index("adm3_pcode")["area_sqkm"].mul(100).to_dict()
    panel["upazila_area_ha"] = panel["upazila_pcode"].map(area_ha)

    # Exposure share: eroded area relative to upazila area (capped at 1)
    panel["erosion_share"] = (panel[erosion_col] / panel["upazila_area_ha"]).clip(0, 1)

    # D_struct — building footprint in eroded zone × PWD replacement cost
    panel["pwd_usd_m2"] = panel.apply(lambda r: building_unit_cost(r, params), axis=1)
    panel["D_struct_usd"] = panel["footprint_m2"] * panel["erosion_share"] * panel["pwd_usd_m2"]

    # D_displace — persons in eroded zone × migration + income disruption
    disp = params["displacement"]
    panel["persons_eroded"] = panel["pop_density_km2"].fillna(0) * panel[erosion_col] / 100
    panel["households_eroded"] = panel["persons_eroded"] / disp["household_size"]
    disruption_usd = disp["daily_wage_usd"] * 30 * disp["disruption_months"]
    panel["D_displace_usd"] = panel["households_eroded"] * (disp["migration_cost_usd"] + disruption_usd)

    # D_ecosys — soil carbon + GMW mangrove fishery (coastal upazilas)
    eco = params["ecosystem"]
    fishery = eco.get("fishery", {})
    mangrove_usd_ha = fishery.get("mangrove_usd_per_ha_yr", eco["mangrove_usd_per_ha_yr"])

    panel["carbon_t_eroded"] = panel[erosion_col] * panel["ocs_t_ha"].fillna(0)
    panel["co2e_t_eroded"] = panel["carbon_t_eroded"] * eco["co2e_per_t_c"]
    panel["D_ecosys_soil_usd"] = panel["co2e_t_eroded"] * eco["scc_usd_per_tco2e"]

    panel["mangrove_flag"] = panel["district_name"].apply(lambda d: is_mangrove_district(d, params))
    gmw_path = ROOT / cfg["paths"]["processed_ecosystem"] / "gmw_mangrove_frac_upazila_year.parquet"
    if gmw_path.exists():
        gmw = pd.read_parquet(gmw_path)
        # Use 2020 snapshot for all years (biennial GMW); forward-fill by upazila
        snap = gmw.sort_values("year").groupby("upazila_pcode").tail(1)[["upazila_pcode", "mangrove_frac"]]
        panel = panel.drop(columns=["mangrove_frac"], errors="ignore")
        panel = panel.merge(snap, on="upazila_pcode", how="left")
        panel["mangrove_frac"] = panel["mangrove_frac"].fillna(0)
        panel["D_ecosys_mangrove_usd"] = panel[erosion_col] * panel["mangrove_frac"] * mangrove_usd_ha
        panel["mangrove_source"] = "gmw_v3"
    else:
        panel["D_ecosys_mangrove_usd"] = 0.0
        m = panel["mangrove_flag"]
        panel.loc[m, "D_ecosys_mangrove_usd"] = (
            panel.loc[m, erosion_col] * mangrove_usd_ha * 0.3
        )
        panel["mangrove_source"] = "district_proxy"
    panel["D_ecosys_usd"] = panel["D_ecosys_soil_usd"] + panel["D_ecosys_mangrove_usd"]

    # D_land — three parallel methods (data_plan Layer 2)
    ntl = params["land_ntl"]
    panel["D_land_ntl_usd"] = panel[erosion_col] * panel["ntl_mean"].fillna(0) * ntl["usd_per_ntl_unit_ha"]

    ntl_idx_path = ROOT / "data/processed/landuse/ntl_land_value_index_upazila.parquet"
    if ntl_idx_path.exists():
        panel = panel.drop(columns=["ntl_land_index"], errors="ignore")
        ntl_idx = pd.read_parquet(ntl_idx_path)
        panel = panel.merge(ntl_idx, on="upazila_pcode", how="left")
        panel["D_land_ntl_fitted_usd"] = (
            panel[erosion_col] * panel["ntl_land_index"].fillna(0) * ntl["usd_per_ntl_unit_ha"]
        )
    else:
        panel["D_land_ntl_fitted_usd"] = panel["D_land_ntl_usd"]

    bt = params["benefit_transfer"]
    panel["D_land_transfer_usd"] = panel[erosion_col] * bt["usd_per_ha_mid"]
    panel["D_land_transfer_low_usd"] = panel[erosion_col] * bt["usd_per_ha_low"]
    panel["D_land_transfer_high_usd"] = panel[erosion_col] * bt["usd_per_ha_high"]

    # D_ag_flow sensitivity — SPAM production × price when available, else cropland proxy
    panel = panel.drop(
        columns=[c for c in panel.columns if c.startswith("rice_price_usd_tonne")],
        errors="ignore",
    )
    rice_path = ROOT / "data/processed/landuse/faostat_rice_price_year.parquet"
    if rice_path.exists():
        prices = pd.read_parquet(rice_path)
        panel = panel.merge(prices[["year", "rice_price_usd_tonne"]], on="year", how="left")
    if "rice_price_usd_tonne" not in panel.columns:
        panel["rice_price_usd_tonne"] = params["npv"]["rice_price_usd_tonne"]
    else:
        panel["rice_price_usd_tonne"] = panel["rice_price_usd_tonne"].fillna(params["npv"]["rice_price_usd_tonne"])

    spam_path = ROOT / "data/processed/landuse/spam_production_upazila.parquet"
    if spam_path.exists():
        if "spam_production_t" not in panel.columns:
            panel = panel.merge(pd.read_parquet(spam_path), on="upazila_pcode", how="left")
        cropland_ha = panel["upazila_area_ha"] * panel["cropland_frac_primary"].fillna(0)
        has_cropland = cropland_ha >= 100  # min 100 ha cropland for NPV
        crop_income_per_ha = np.where(
            has_cropland,
            panel["spam_production_t"].fillna(0) / cropland_ha * panel["rice_price_usd_tonne"],
            0.0,
        )
        crop_income_per_ha = np.clip(crop_income_per_ha, 0, 8000)  # cap ~$8k/ha/yr income
        for r in params["npv"]["discount_rates"]:
            land_val = np.clip(crop_income_per_ha / r, 0, 50000)
            panel[f"D_land_npv_r{int(r*100)}_usd"] = panel[erosion_col] * land_val
        panel["D_land_npv_usd"] = panel["D_land_npv_r7_usd"]
        panel["D_ag_flow_usd"] = (
            panel["erosion_share"] * panel["spam_production_t"].fillna(0) * panel["rice_price_usd_tonne"]
        )
        panel["D_ag_source"] = "spam2020_production"
    else:
        panel["D_land_npv_usd"] = panel["D_land_transfer_usd"]
        panel["D_ag_flow_usd"] = (
            panel[erosion_col]
            * panel["cropland_frac_primary"].fillna(0)
            * 4.0
            * panel["rice_price_usd_tonne"]
        )
        panel["D_ag_source"] = "cropland_proxy"

    panel["D_total_asset_usd"] = (
        panel["D_land_ntl_usd"] + panel["D_struct_usd"] + panel["D_displace_usd"] + panel["D_ecosys_usd"]
    )
    panel["D_total_asset_npv_usd"] = (
        panel["D_land_npv_usd"] + panel["D_struct_usd"] + panel["D_displace_usd"] + panel["D_ecosys_usd"]
    )
    panel["D_total_asset_transfer_usd"] = (
        panel["D_land_transfer_usd"] + panel["D_struct_usd"] + panel["D_displace_usd"] + panel["D_ecosys_usd"]
    )

    out_dir = ROOT / "data/processed/panel"
    land_cols = [
        "D_land_ntl_usd", "D_land_ntl_fitted_usd", "D_land_npv_usd",
        "D_land_transfer_usd", "D_land_transfer_low_usd", "D_land_transfer_high_usd",
    ]
    if spam_path.exists():
        land_cols += [f"D_land_npv_r{int(r*100)}_usd" for r in params["npv"]["discount_rates"]]
    damage_cols = [
        "upazila_pcode", "year", erosion_col, "erosion_share", "mangrove_frac", "mangrove_source",
        *land_cols,
        "D_struct_usd", "D_displace_usd",
        "D_ecosys_soil_usd", "D_ecosys_mangrove_usd", "D_ecosys_usd",
        "D_total_asset_usd", "D_total_asset_npv_usd", "D_total_asset_transfer_usd",
        "D_ag_flow_usd",
    ]
    damage = panel[[c for c in damage_cols if c in panel.columns]].copy()
    damage.to_parquet(out_dir / "damage_upazila_year.parquet", index=False)

    nat_cols = [
        "D_land_ntl_usd", "D_land_npv_usd", "D_land_transfer_usd",
        "D_struct_usd", "D_displace_usd", "D_ecosys_usd",
        "D_total_asset_usd", "D_total_asset_npv_usd", "D_total_asset_transfer_usd",
        "D_ag_flow_usd",
    ]
    national = damage.groupby("year")[[c for c in nat_cols if c in damage.columns]].sum().reset_index()
    national.to_csv(ROOT / "output/tables/national_damage_by_year.csv", index=False)

    # Land-method bounds summary (2000–2020)
    sub = national[national["year"].between(2000, 2020)]
    bounds = pd.DataFrame([{
        "period": "2000-2020",
        "D_land_ntl_mean_usd_yr": sub["D_land_ntl_usd"].mean(),
        "D_land_npv_mean_usd_yr": sub["D_land_npv_usd"].mean(),
        "D_land_transfer_mean_usd_yr": sub["D_land_transfer_usd"].mean(),
        "D_total_ntl_mean_usd_yr": sub["D_total_asset_usd"].mean(),
        "D_total_npv_mean_usd_yr": sub["D_total_asset_npv_usd"].mean(),
        "D_total_transfer_mean_usd_yr": sub["D_total_asset_transfer_usd"].mean(),
    }])
    bounds.to_csv(ROOT / "output/tables/d_land_method_bounds.csv", index=False)

    panel.to_parquet(out_dir / "panel_upazila_year.parquet", index=False)
    panel.to_csv(out_dir / "panel_upazila_year.csv", index=False)

    latest = national[national["year"].between(2000, 2020)]
    print(f"Damage panel: {len(damage)} rows")
    print(f"Mean annual D_total_asset (2000–2020): ${latest['D_total_asset_usd'].mean():,.0f} USD")
    print(f"Saved → panel/damage_upazila_year.parquet, output/tables/national_damage_by_year.csv")


if __name__ == "__main__":
    main()
