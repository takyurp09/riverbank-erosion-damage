#!/usr/bin/env python3
"""D_land Method A: NTL land-value index from cross-sectional regression on land characteristics."""

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

    # Cross-section: mean NTL 2012–2020 per upazila (where VIIRS exists)
    sub = panel[panel["year"].between(2012, 2020) & panel["ntl_mean"].notna()].copy()
    xs = (
        sub.groupby("upazila_pcode")
        .agg(
            ntl_mean=("ntl_mean", "mean"),
            cropland_frac=("cropland_frac_primary", "mean"),
            pop_density_km2=("pop_density_km2", "mean"),
            road_density_km_km2=("road_density_km_km2", "mean"),
            embankment_km=("embankment_km", "mean"),
        )
        .reset_index()
    )
    xs = xs[xs["ntl_mean"] > 0].copy()
    xs["log_ntl"] = np.log1p(xs["ntl_mean"])

    formula = "log_ntl ~ cropland_frac + pop_density_km2 + road_density_km_km2 + embankment_km"
    model = smf.ols(formula, data=xs).fit()

    xs["ntl_land_index"] = np.expm1(model.predict(xs))
    xs["ntl_land_index"] = xs["ntl_land_index"].clip(lower=0)

    coefs = pd.DataFrame(
        {"term": model.params.index, "coef": model.params.values, "se": model.bse.values, "pvalue": model.pvalues.values}
    )
    coefs.to_csv(out / "ntl_land_value_regression_coefs.csv", index=False)
    xs[["upazila_pcode", "ntl_land_index"]].to_parquet(
        ROOT / "data/processed/landuse/ntl_land_value_index_upazila.parquet", index=False
    )

    summary = {"n_upazilas": len(xs), "r2": model.rsquared}
    pd.DataFrame([summary]).to_csv(out / "ntl_land_value_regression_summary.csv", index=False)
    print(f"NTL land-value regression: n={len(xs)}, R²={model.rsquared:.3f}")


if __name__ == "__main__":
    main()
