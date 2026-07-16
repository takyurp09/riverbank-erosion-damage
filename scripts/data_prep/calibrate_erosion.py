#!/usr/bin/env python3
"""Calibrate erosion to BWDB national benchmark; write calibrated ha column."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def load_params() -> dict:
    with open(ROOT / "config" / "damage_params.yaml") as f:
        return yaml.safe_load(f)


def apply_calibration(panel: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    params = params or load_params()
    cal = params["erosion_calibration"]
    src = cal["source_col"]
    if src not in panel.columns:
        raise KeyError(f"Missing erosion column: {src}")

    y0, y1 = cal["benchmark_years"]
    national = panel.groupby("year")[src].sum()
    observed = national.loc[y0:y1].mean()
    target = cal["benchmark_ha_yr"]
    scale = target / observed if observed > 0 else 1.0

    panel = panel.copy()
    panel["erosion_cal_scale"] = scale
    panel["erosion_gross_ha_calibrated"] = panel[src] * scale

    # Landsat river + S2 end at erosion_years_end; do not report calibrated 0 for later years
    try:
        with open(ROOT / "config" / "settings.yaml") as f:
            cfg = yaml.safe_load(f)
        y_end = int(cfg["gee"].get("erosion_years_end", cfg["gee"]["years_end"]))
        panel.loc[panel["year"] > y_end, "erosion_gross_ha_calibrated"] = np.nan
    except Exception:
        pass

    return panel


def write_calibration_summary(panel: pd.DataFrame, params: dict | None = None) -> float:
    params = params or load_params()
    cal = params["erosion_calibration"]
    src = cal["source_col"]
    y0, y1 = cal["benchmark_years"]
    national = panel.groupby("year")[src].sum()
    observed = national.loc[y0:y1].mean()
    scale = panel["erosion_cal_scale"].iloc[0]

    out_dir = ROOT / "data/processed/erosion"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {"metric": "source_col", "value": src},
            {"metric": "benchmark_ha_yr", "value": cal["benchmark_ha_yr"]},
            {"metric": "observed_mean_ha_yr", "value": round(observed, 1)},
            {"metric": "calibration_scale", "value": round(scale, 6)},
            {"metric": "calibrated_mean_ha_yr", "value": round(national.loc[y0:y1].mean() * scale, 1)},
        ]
    )
    summary.to_csv(out_dir / "erosion_calibration_summary.csv", index=False)
    return scale


def main() -> None:
    params = load_params()
    panel_path = ROOT / "data/processed/panel/panel_upazila_year.parquet"
    panel = pd.read_parquet(panel_path)
    panel = apply_calibration(panel, params)
    scale = write_calibration_summary(panel, params)

    panel.to_parquet(panel_path, index=False)
    panel.to_csv(ROOT / "data/processed/panel/panel_upazila_year.csv", index=False)
    cal = params["erosion_calibration"]
    src = cal["source_col"]
    observed = panel.groupby("year")[src].sum().loc[cal["benchmark_years"][0] : cal["benchmark_years"][1]].mean()
    print(f"Calibration scale: {scale:.4f} ({src} {observed:,.0f} → {cal['benchmark_ha_yr']:,.0f} ha/yr)")
    print("Updated panel with erosion_gross_ha_calibrated")


if __name__ == "__main__":
    main()
