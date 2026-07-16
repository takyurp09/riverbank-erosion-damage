#!/usr/bin/env python3
"""Phase 5: heterogeneity — damage per unit erosion × embankment + population density."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)

    df = panel[
        panel["year"].between(2000, 2020)
        & panel["D_total_asset_usd"].notna()
        & (panel["D_total_asset_usd"] > 0)
        & panel["erosion_gross_ha_calibrated"].notna()
        & (panel["erosion_gross_ha_calibrated"] > 0)
    ].copy()

    df["log_damage"] = np.log1p(df["D_total_asset_usd"])
    df["erosion"] = df["erosion_gross_ha_calibrated"]
    df["embankment_km"] = df["embankment_km"].fillna(0)
    df["pop_density_km2"] = df["pop_density_km2"].fillna(0)

    formula = (
        "log_damage ~ erosion * embankment_km + erosion * pop_density_km2 + C(upazila_pcode) + C(year)"
    )
    model = smf.ols(formula, data=df).fit(cov_type="cluster", cov_kwds={"groups": df["district_pcode"]})

    keep = ["Intercept", "erosion", "embankment_km", "pop_density_km2",
            "erosion:embankment_km", "erosion:pop_density_km2"]
    coefs = pd.DataFrame(
        {
            "term": model.params.index,
            "coef": model.params.values,
            "se": model.bse.values,
            "pvalue": model.pvalues.values,
        }
    )
    coefs = coefs[coefs["term"].isin(keep)]
    coefs.to_csv(out / "heterogeneity_regression_coefs.csv", index=False)

    pd.DataFrame([{"n_obs": len(df), "r2": model.rsquared}]).to_csv(
        out / "heterogeneity_regression_summary.csv", index=False
    )
    print(f"Heterogeneity regression: n={len(df)}, R²={model.rsquared:.3f}")
    print(f"Saved → output/tables/heterogeneity_regression_coefs.csv")


if __name__ == "__main__":
    main()
