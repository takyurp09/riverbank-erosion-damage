#!/usr/bin/env python3
"""WorldPop Global2 vs Global1 extrapolation — D_displace sensitivity (2021–2024).

Uses national population totals from Global2 rasters (rasterio sum) scaled to upazila
shares from the panel when zonal extraction is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
GLOBAL2_URL = (
    "https://worldpop-public-data.soton.ac.uk/GIS/Population/Global_2015_2030/R2024B/"
    "{year}/BGD/v1/100m/unconstrained/bgd_pop_{year}_UC_100m_R2024B_v1.tif"
)


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def download_global2(year: int, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return True
    url = GLOBAL2_URL.format(year=year)
    try:
        with requests.get(url, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return True
    except requests.RequestException as exc:
        print(f"  Global2 {year} download failed: {exc}")
        return False


def national_pop_from_tif(tif: Path) -> float:
    with rasterio.open(tif) as src:
        data = src.read(1, masked=True)
        return float(np.ma.filled(data, 0).sum())


def displacement_usd(panel: pd.DataFrame, pop_density_col: str, params: dict) -> pd.Series:
    disp = params["displacement"]
    erosion = panel["erosion_gross_ha_calibrated"].fillna(0)
    persons = panel[pop_density_col].fillna(0) * erosion / 100
    hh = persons / disp["household_size"]
    disruption = disp["daily_wage_usd"] * 30 * disp["disruption_months"]
    return hh * (disp["migration_cost_usd"] + disruption)


def main() -> None:
    cfg = load_config()
    with open(ROOT / "config" / "damage_params.yaml") as f:
        params = yaml.safe_load(f)

    raw_dir = ROOT / cfg["paths"]["raw"] / "worldpop_global2"
    raw_dir.mkdir(parents=True, exist_ok=True)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    sub = panel[panel["year"].between(2021, 2024)].copy()

    rows = []
    for year in range(2021, 2025):
        tif = raw_dir / f"bgd_pop_{year}_global2.tif"
        if not download_global2(year, tif):
            continue
        nat_g2 = national_pop_from_tif(tif)
        tif.unlink(missing_ok=True)

        yr = sub[sub["year"] == year].copy()
        nat_g1 = yr["pop_total"].sum()
        scale = nat_g2 / nat_g1 if nat_g1 > 0 else 1.0
        yr["pop_density_global2_km2"] = yr["pop_density_km2"] * scale
        yr["D_displace_global1_usd"] = displacement_usd(yr, "pop_density_km2", params)
        yr["D_displace_global2_usd"] = displacement_usd(yr, "pop_density_global2_km2", params)
        rows.append({
            "year": year,
            "pop_global1": nat_g1,
            "pop_global2": nat_g2,
            "scale_global2_over_global1": scale,
            "D_displace_global1": yr["D_displace_global1_usd"].sum(),
            "D_displace_global2": yr["D_displace_global2_usd"].sum(),
        })

    if not rows:
        print("No Global2 years processed — skipping")
        return

    summary = pd.DataFrame(rows)
    summary["ratio_global2_global1"] = summary["D_displace_global2"] / summary["D_displace_global1"].replace(0, np.nan)

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "robustness_worldpop_global2_displace.csv", index=False)
    print(f"Global2 displacement robustness → {out.name}/robustness_worldpop_global2_displace.csv")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
