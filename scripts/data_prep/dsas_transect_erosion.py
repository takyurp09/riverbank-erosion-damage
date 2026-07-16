#!/usr/bin/env python3
"""DSAS-style shoreline erosion rates: transects perpendicular to HydroRIVERS, aggregated to upazila."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def cast_transects(rivers: gpd.GeoDataFrame, spacing_m: float = 5000) -> gpd.GeoDataFrame:
    """Perpendicular transect segments at spacing along each reach (local UTM)."""
    rows = []
    for _, reach in rivers.iterrows():
        line = reach.geometry
        if line is None or line.is_empty:
            continue
        length = line.length
        if length < spacing_m:
            positions = [0.5]
        else:
            n = max(2, int(length // spacing_m))
            positions = np.linspace(0.05, 0.95, n)
        for frac in positions:
            pt = line.interpolate(frac, normalized=True)
            d1 = max(frac - 0.01, 0)
            d2 = min(frac + 0.01, 1)
            p1 = line.interpolate(d1, normalized=True)
            p2 = line.interpolate(d2, normalized=True)
            dx, dy = p2.x - p1.x, p2.y - p1.y
            norm = np.hypot(dx, dy) or 1.0
            # Perpendicular unit vector
            px, py = -dy / norm, dx / norm
            half = 2500  # 2.5 km each side → 5 km transect
            from shapely.geometry import LineString

            transect = LineString([
                (pt.x - px * half, pt.y - py * half),
                (pt.x + px * half, pt.y + py * half),
            ])
            rows.append({
                "river_reach_id": int(reach["HYRIV_ID"]),
                "transect_id": f"{int(reach['HYRIV_ID'])}_{frac:.3f}",
                "geometry": transect,
            })
    return gpd.GeoDataFrame(rows, crs=rivers.crs)


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    hydro = ROOT / cfg["paths"]["processed_hydro"]
    erosion_dir = ROOT / cfg["paths"]["processed_erosion"]
    out_dir = erosion_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    assign = pd.read_csv(hydro / "upazila_river_reach.csv")
    reach_ids = assign["river_reach_id"].dropna().unique().astype(int)

    rivers = gpd.read_file(hydro / "hydrorivers_bgd.gpkg")
    min_dis = 50
    rivers = rivers[(rivers["HYRIV_ID"].isin(reach_ids)) | (rivers["DIS_AV_CMS"] >= min_dis)].copy()
    study_crs = cfg["project"]["study_crs"]
    rivers = rivers.to_crs(study_crs)

    transects = cast_transects(rivers, spacing_m=5000)
    transects = transects.to_crs(cfg["project"]["crs"])

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["crs"])

    # Assign transects to upazilas by intersection
    joined = gpd.sjoin(transects, upazila[["adm3_pcode", "geometry"]], how="left", predicate="intersects")
    joined = joined.rename(columns={"adm3_pcode": "upazila_pcode"})

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    erosion_col = "erosion_gross_ha_calibrated" if "erosion_gross_ha_calibrated" in panel.columns else "erosion_gross_ha_2yr_river"

    # Transect count per upazila
    n_transects = joined.groupby("upazila_pcode").size().rename("n_transects")

    # EPR proxy (m/yr): erosion ha / (shoreline length proxy) — shoreline ≈ n_transects × 5 km
    epr_rows = []
    sub = panel[panel["year"].between(2000, 2020)]
    for pcode, grp in sub.groupby("upazila_pcode"):
        n_t = n_transects.get(pcode, 0)
        if n_t == 0:
            continue
        shoreline_m = n_t * 5000
        mean_ha_yr = grp[erosion_col].mean()
        # ha/yr → m²/yr, divided by shoreline length → m/yr retreat rate
        epr_m_yr = (mean_ha_yr * 10_000) / shoreline_m if shoreline_m > 0 else 0
        epr_rows.append({
            "upazila_pcode": pcode,
            "n_transects": n_t,
            "shoreline_km": shoreline_m / 1000,
            "mean_erosion_ha_yr": mean_ha_yr,
            "epr_m_yr": epr_m_yr,
        })

    epr = pd.DataFrame(epr_rows)
    epr.to_parquet(out_dir / "dsas_epr_upazila.parquet", index=False)

    # National summary by river system
    dist = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_district.gpkg")
    dmap = dist.set_index("adm2_pcode")["adm2_name"].to_dict()
    upa_map = upazila.set_index("adm3_pcode")["adm2_pcode"].to_dict()
    epr["district_name"] = epr["upazila_pcode"].map(lambda p: dmap.get(upa_map.get(p, ""), ""))

    systems = {
        "Jamuna": ["Sirajganj", "Gaibandha", "Kurigram", "Jamalpur", "Bogura"],
        "Padma": ["Manikganj", "Rajbari", "Shariatpur", "Madaripur", "Faridpur"],
        "Meghna": ["Chandpur", "Bhola", "Lakshmipur", "Noakhali", "Barishal"],
    }
    nat_rows = []
    for system, districts in systems.items():
        m = epr[epr["district_name"].isin(districts)]
        if len(m):
            nat_rows.append({
                "river_system": system,
                "mean_epr_m_yr": m["epr_m_yr"].mean(),
                "median_epr_m_yr": m["epr_m_yr"].median(),
                "n_upazilas": len(m),
            })

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(nat_rows).to_csv(out / "dsas_epr_by_river_system.csv", index=False)
    epr.nlargest(25, "epr_m_yr").to_csv(out / "dsas_epr_top25_upazilas.csv", index=False)

    transects.to_file(out_dir / "dsas_transects.gpkg", driver="GPKG")
    print(f"DSAS EPR → {out_dir.name}/dsas_epr_upazila.parquet ({len(epr)} upazilas)")
    print(f"Transects → {out_dir.name}/dsas_transects.gpkg ({len(transects)} segments)")


if __name__ == "__main__":
    main()
