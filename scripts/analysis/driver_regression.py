#!/usr/bin/env python3
"""Phase 4: driver regression — erosion ~ discharge anomaly + precip + SPEI (upazila FE)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[2]
FORMULA = "log_erosion ~ discharge_anomaly_pct + precip_anomaly_pct + spei3_mean + C(upazila_pcode)"


def prep_df(panel: pd.DataFrame, year_start: int, year_end: int) -> pd.DataFrame:
    erosion_col = "erosion_gross_ha_calibrated"
    df = panel[
        panel["year"].between(year_start, year_end)
        & panel[erosion_col].notna()
        & (panel[erosion_col] > 0)
    ].copy()
    df["log_erosion"] = np.log1p(df[erosion_col])
    for col in ("discharge_anomaly_pct", "precip_anomaly_pct", "spei3_mean"):
        df[col] = df[col].fillna(0) if col in df.columns else 0.0
    return df


def fit_clustered(df: pd.DataFrame, groups) -> smf.regression.linear_model.RegressionResultsWrapper:
    return smf.ols(FORMULA, data=df).fit(cov_type="cluster", cov_kwds={"groups": groups})


def main() -> None:
    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    out_dir = ROOT / "output/tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = prep_df(panel, 2000, 2020)
    model = fit_clustered(df, df["district_pcode"])

    coefs = pd.DataFrame(
        {
            "term": model.params.index,
            "coef": model.params.values,
            "se": model.bse.values,
            "pvalue": model.pvalues.values,
        }
    )
    coefs = coefs[~coefs["term"].str.contains("upazila_pcode", na=False)]
    coefs.to_csv(out_dir / "driver_regression_coefs.csv", index=False)

    summary = {
        "n_obs": len(df),
        "r2": model.rsquared,
        "erosion_col": "erosion_gross_ha_calibrated",
        "discharge_source": df["discharge_source"].iloc[0] if "discharge_source" in df.columns else "unknown",
        "cluster": "district",
    }
    pd.DataFrame([summary]).to_csv(out_dir / "driver_regression_summary.csv", index=False)

    # Cluster robustness: district (main), river reach, two-way (upazila × year)
    cluster_rows = []
    for label, groups in [
        ("district", df["district_pcode"]),
        ("river_reach", df["river_reach_id"].fillna("unknown")),
        ("two_way", df["upazila_pcode"].astype(str) + "_" + df["year"].astype(str)),
    ]:
        m = fit_clustered(df, groups)
        for term in ("discharge_anomaly_pct", "precip_anomaly_pct", "spei3_mean"):
            cluster_rows.append({
                "cluster_type": label,
                "term": term,
                "coef": m.params.get(term, np.nan),
                "se": m.bse.get(term, np.nan),
                "pvalue": m.pvalues.get(term, np.nan),
                "r2": m.rsquared,
                "n_obs": len(df),
            })
    pd.DataFrame(cluster_rows).to_csv(out_dir / "robustness_driver_cluster_se.csv", index=False)

    print(f"Driver regression: n={summary['n_obs']}, R²={summary['r2']:.3f}")
    print(f"Saved → output/tables/driver_regression_coefs.csv, robustness_driver_cluster_se.csv")


if __name__ == "__main__":
    main()
