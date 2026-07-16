#!/usr/bin/env python3
"""Harmonize ISIMIP3b discharge to GloFAS via per-reach linear bias correction (historical 1991–2014)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def calibrate_reach_gcm(sub: pd.DataFrame) -> tuple[float, float]:
    """Return (alpha, beta) for discharge_glofas ≈ alpha + beta * discharge_isimip."""
    x = sub["discharge_cms_isimip"].values
    y = sub["discharge_cms_glofas"].values
    mask = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if mask.sum() < 5:
        return 0.0, 1.0
    x, y = x[mask], y[mask]
    beta = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 1.0
    alpha = y.mean() - beta * x.mean()
    return float(alpha), float(beta)


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    hydro = ROOT / cfg["paths"]["processed_hydro"]
    isimip = pd.read_parquet(hydro / "isimip_reach_discharge_year.parquet")
    glofas = pd.read_parquet(hydro / "glofas_reach_discharge_year.parquet")

    hist = isimip[isimip["scenario"] == "historical"].copy()
    calib_period = hist["year"].between(1991, 2014)
    merged = hist[calib_period].merge(
        glofas.rename(columns={"discharge_cms": "discharge_cms_glofas", "discharge_anomaly_pct": "anom_glofas"}),
        on=["river_reach_id", "year"],
        how="inner",
    ).rename(columns={"discharge_cms": "discharge_cms_isimip", "discharge_anomaly_pct": "anom_isimip"})

    coef_rows = []
    for (reach, gcm), sub in merged.groupby(["river_reach_id", "gcm"]):
        alpha, beta = calibrate_reach_gcm(sub)
        sub = sub.copy()
        sub["discharge_cms_calibrated"] = alpha + beta * sub["discharge_cms_isimip"]
        r_raw = sub["discharge_cms_isimip"].corr(sub["discharge_cms_glofas"])
        r_cal = sub["discharge_cms_calibrated"].corr(sub["discharge_cms_glofas"])
        coef_rows.append({
            "river_reach_id": reach,
            "gcm": gcm,
            "alpha": alpha,
            "beta": beta,
            "n_years": len(sub),
            "corr_raw": r_raw,
            "corr_calibrated": r_cal,
        })

    coefs = pd.DataFrame(coef_rows)
    coefs.to_csv(hydro / "isimip_glofas_calibration_coefs.csv", index=False)

    # Apply calibration to full ISIMIP panel
    isimip = isimip.merge(coefs[["river_reach_id", "gcm", "alpha", "beta"]], on=["river_reach_id", "gcm"], how="left")
    isimip["alpha"] = isimip["alpha"].fillna(0)
    isimip["beta"] = isimip["beta"].fillna(1)
    isimip["discharge_cms_raw"] = isimip["discharge_cms"]
    isimip["discharge_cms"] = isimip["alpha"] + isimip["beta"] * isimip["discharge_cms_raw"]

    # Recompute anomalies on calibrated discharge
    baseline = (
        isimip[isimip["year"].between(1990, 2020)]
        .groupby(["river_reach_id", "gcm"])["discharge_cms"]
        .mean()
        .rename("discharge_baseline_cms")
        .reset_index()
    )
    isimip = isimip.drop(columns=["discharge_baseline_cms", "discharge_anomaly_pct"], errors="ignore")
    isimip = isimip.merge(baseline, on=["river_reach_id", "gcm"], how="left")
    isimip["discharge_anomaly_pct"] = (
        (isimip["discharge_cms"] - isimip["discharge_baseline_cms"])
        / isimip["discharge_baseline_cms"]
        * 100
    )

    out_path = hydro / "isimip_reach_discharge_year.parquet"
    isimip.to_parquet(out_path, index=False)

    # Validation table (use raw + calibrated columns)
    val = isimip[isimip["scenario"] == "historical"].copy()
    val = val[val["year"].between(1991, 2014)]
    val = val.merge(
        glofas.rename(columns={"discharge_cms": "discharge_cms_glofas"}),
        on=["river_reach_id", "year"],
        how="inner",
    )

    rows = []
    for gcm, g in val.groupby("gcm"):
        rows.append({
            "gcm": gcm,
            "n_reach_years": len(g),
            "corr_raw": g["discharge_cms_raw"].corr(g["discharge_cms_glofas"]),
            "corr_calibrated": g["discharge_cms"].corr(g["discharge_cms_glofas"]),
            "mean_bias_pct_raw": ((g["discharge_cms_raw"] - g["discharge_cms_glofas"]) / g["discharge_cms_glofas"]).mean() * 100,
            "mean_bias_pct_calibrated": ((g["discharge_cms"] - g["discharge_cms_glofas"]) / g["discharge_cms_glofas"]).mean() * 100,
        })

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "isimip_glofas_validation.csv", index=False)

    # Refresh upazila ISIMIP discharge for SSP
    assign = pd.read_csv(hydro / "upazila_river_reach.csv")
    future = isimip[isimip["year"] >= 2025].copy()
    merged_upa = assign.merge(
        future.rename(columns={"river_reach_id": "main_river_flag"}),
        on="main_river_flag",
        how="inner",
    )
    upa_dis = merged_upa.groupby(["upazila_pcode", "year", "gcm", "scenario"]).first().reset_index()
    upa_dis.to_parquet(ROOT / "data/processed/panel/isimip_upazila_discharge.parquet", index=False)

    print(f"ISIMIP calibrated → {out_path.name}")
    print(f"Mean per-GCM r: raw {pd.DataFrame(rows).corr_raw.mean():.3f} → calibrated {pd.DataFrame(rows).corr_calibrated.mean():.3f}")
    for r in rows:
        print(f"  {r['gcm']}: r={r['corr_calibrated']:.3f} (was {r['corr_raw']:.3f})")


if __name__ == "__main__":
    main()
