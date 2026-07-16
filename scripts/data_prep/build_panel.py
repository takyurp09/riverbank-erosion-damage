#!/usr/bin/env python3
"""Build merged upazila × year panel from all processed layers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from calibrate_erosion import apply_calibration, write_calibration_summary

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def read_if_exists(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.exists() else None


def main() -> None:
    cfg = load_config()
    out_dir = ROOT / "data/processed/panel"
    out_dir.mkdir(parents=True, exist_ok=True)

    jrc = pd.read_parquet(ROOT / cfg["paths"]["processed_erosion"] / "jrc_erosion_upazila_year.parquet")
    reach = pd.read_csv(ROOT / cfg["paths"]["processed_hydro"] / "upazila_river_reach.csv")

    base = jrc[["upazila_pcode", "district_pcode", "upazila_name", "year"]].drop_duplicates()

    for extra in [
        read_if_exists(ROOT / cfg["paths"]["processed_erosion"] / "landsat_erosion_2yr_upazila_year.parquet"),
        read_if_exists(ROOT / cfg["paths"]["processed_climate"] / "spei3_upazila_year.parquet"),
    ]:
        if extra is not None:
            cols = ["upazila_pcode", "year"] + [c for c in ["district_pcode", "upazila_name"] if c in extra.columns]
            base = pd.concat([base, extra[cols]]).drop_duplicates(["upazila_pcode", "year"])

    panel = base.merge(
        jrc[["upazila_pcode", "year", "erosion_gross_ha_1yr", "erosion_gross_ha_2yr"]],
        on=["upazila_pcode", "year"],
        how="left",
    )

    merges = [
        (ROOT / cfg["paths"]["processed_erosion"] / "landsat_erosion_2yr_upazila_year.parquet",
         ["upazila_pcode", "year", "erosion_gross_ha_2yr_landsat"]),
        (ROOT / cfg["paths"]["processed_erosion"] / "landsat_erosion_2yr_river_upazila_year.parquet",
         ["upazila_pcode", "year", "erosion_gross_ha_2yr_river_landsat"]),
        (ROOT / cfg["paths"]["processed_erosion"] / "jrc_erosion_river_upazila_year.parquet",
         ["upazila_pcode", "year", "erosion_gross_ha_1yr_river", "erosion_gross_ha_2yr_river"]),
        (ROOT / cfg["paths"]["processed_population"] / "worldpop_upazila_year.parquet",
         ["upazila_pcode", "year", "pop_total", "pop_density_km2"]),
        (ROOT / cfg["paths"]["processed_population"] / "ghsl_pop_upazila_year.parquet",
         ["upazila_pcode", "year", "ghsl_pop"]),
        (ROOT / cfg["paths"]["processed_climate"] / "era5_precip_upazila_year.parquet",
         ["upazila_pcode", "year", "era5_precip_mm", "era5_precip_anomaly_pct"]),
        (ROOT / cfg["paths"]["processed_climate"] / "spei3_upazila_year.parquet",
         ["upazila_pcode", "year", "spei3_mean"]),
        (ROOT / cfg["paths"]["processed_climate"] / "chirps_upazila_year.parquet",
         ["upazila_pcode", "year", "precip_mm", "precip_anomaly_pct"]),
        (ROOT / "data/processed/landuse/cropland_upazila_year.parquet",
         None),  # dynamic cols
        (ROOT / cfg["paths"]["processed_infrastructure"] / "open_buildings_upazila.parquet",
         ["upazila_pcode", "n_buildings", "footprint_m2"]),
        (ROOT / cfg["paths"]["processed_infrastructure"] / "ntl_viirs_upazila_year.parquet",
         ["upazila_pcode", "year", "ntl_mean"]),
        (ROOT / cfg["paths"]["processed_infrastructure"] / "osm_infrastructure_upazila.parquet",
         ["upazila_pcode", "road_km", "road_density_km_km2", "embankment_km"]),
        (ROOT / cfg["paths"]["processed_erosion"] / "s2_erosion_2yr_river_upazila_year.parquet",
         ["upazila_pcode", "year", "erosion_gross_ha_2yr_s2_river"]),
        (ROOT / cfg["paths"]["processed_erosion"] / "jrc_net_erosion_river_upazila_year.parquet",
         ["upazila_pcode", "year", "accretion_gross_ha_1yr", "accretion_gross_ha_2yr",
          "erosion_net_ha_1yr", "erosion_net_ha_2yr"]),
        (ROOT / cfg["paths"]["processed_ecosystem"] / "soilgrids_ocs_upazila.parquet",
         ["upazila_pcode", "ocs_t_ha"]),
        (ROOT / cfg["paths"]["processed_ecosystem"] / "gmw_mangrove_frac_upazila_year.parquet",
         ["upazila_pcode", "year", "mangrove_frac"]),
        (ROOT / cfg["paths"]["processed_erosion"] / "dsas_epr_upazila.parquet",
         ["upazila_pcode", "n_transects", "shoreline_km", "epr_m_yr"]),
    ]

    for path, cols in merges:
        df = read_if_exists(path)
        if df is not None:
            if cols is None:
                cols = ["upazila_pcode", "year"] + [c for c in df.columns if c not in ("upazila_pcode", "year")]
            merge_on = ["upazila_pcode", "year"] if "year" in df.columns else ["upazila_pcode"]
            panel = panel.merge(df[[c for c in cols if c in df.columns]], on=merge_on, how="left")

    if "erosion_gross_ha_2yr_river_landsat" in panel.columns:
        panel["erosion_gross_ha_2yr_primary"] = panel["erosion_gross_ha_2yr_river_landsat"]
        if "erosion_gross_ha_2yr_river" in panel.columns:
            panel["erosion_gross_ha_2yr_primary"] = panel["erosion_gross_ha_2yr_primary"].combine_first(
                panel["erosion_gross_ha_2yr_river"]
            )

    # Cropland exposure per data_plan: MODIS 2001–2014, WorldCover snapshot 2015+
    if "cropland_frac_modis" in panel.columns:
        panel["cropland_frac_primary"] = panel["cropland_frac_modis"]
    if "cropland_frac_worldcover" in panel.columns:
        wc_snap = (
            panel.loc[panel["year"] == 2021, ["upazila_pcode", "cropland_frac_worldcover"]]
            .dropna()
            .drop_duplicates("upazila_pcode")
            .set_index("upazila_pcode")["cropland_frac_worldcover"]
        )
        mask = panel["year"] >= 2015
        panel.loc[mask, "cropland_frac_worldcover"] = panel.loc[mask, "upazila_pcode"].map(wc_snap)
        panel.loc[mask, "cropland_frac_primary"] = panel.loc[mask, "cropland_frac_worldcover"]

    panel = panel.merge(
        reach[["upazila_pcode", "river_reach_id", "reach_discharge_cms", "main_river_flag"]],
        on="upazila_pcode",
        how="left",
    )

    glofas_path = ROOT / cfg["paths"]["processed_hydro"] / "glofas_reach_discharge_year.parquet"
    if glofas_path.exists():
        reach_dis = pd.read_parquet(glofas_path)
        upa_dis = reach.merge(
            reach_dis[["river_reach_id", "year", "discharge_cms", "discharge_anomaly_pct"]],
            on="river_reach_id",
            how="left",
        )[["upazila_pcode", "year", "discharge_cms", "discharge_anomaly_pct"]]
        panel = panel.drop(columns=["discharge_cms", "discharge_anomaly_pct", "discharge_source"], errors="ignore")
        panel = panel.merge(upa_dis, on=["upazila_pcode", "year"], how="left")
        panel["discharge_source"] = "glofas"

    panel = panel.sort_values(["year", "upazila_pcode"]).reset_index(drop=True)

    # Coastal fallback + extend erosion through erosion_years_end (Landsat/S2 when JRC ends)
    from extend_erosion_series import apply_coastal_and_extension

    panel = apply_coastal_and_extension(panel, cfg)

    # Re-apply BWDB erosion calibration after layer merges
    params_path = ROOT / "config" / "damage_params.yaml"
    with open(params_path) as f:
        params = yaml.safe_load(f)
    panel = apply_calibration(panel, params)
    write_calibration_summary(panel, params)
    panel.to_parquet(out_dir / "panel_upazila_year.parquet", index=False)
    panel.to_csv(out_dir / "panel_upazila_year.csv", index=False)

    summary = {
        "n_rows": len(panel),
        "n_upazilas": panel["upazila_pcode"].nunique(),
        "year_min": int(panel["year"].min()),
        "year_max": int(panel["year"].max()),
        "n_cols": len(panel.columns),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "panel_summary.csv", index=False)
    print(f"Panel: {summary['n_rows']} rows, {summary['n_upazilas']} upazilas, {summary['year_min']}–{summary['year_max']}")


if __name__ == "__main__":
    main()
