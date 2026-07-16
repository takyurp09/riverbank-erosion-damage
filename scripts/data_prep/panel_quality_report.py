#!/usr/bin/env python3
"""Panel data-quality summary: coverage, missingness, national erosion totals."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    out_dir = ROOT / "data/processed/panel"
    out_dir.mkdir(parents=True, exist_ok=True)

    numeric = panel.select_dtypes("number").columns
    miss = (panel[numeric].isna().mean() * 100).round(1).sort_values(ascending=False)
    miss.to_csv(out_dir / "panel_missingness_pct.csv", header=["missing_pct"])

    erosion_col = next(
        (c for c in ("erosion_gross_ha_2yr_primary", "erosion_gross_ha_2yr_river", "erosion_gross_ha_2yr") if c in panel.columns),
        None,
    )
    rows = [
        {"metric": "n_rows", "value": len(panel)},
        {"metric": "n_upazilas", "value": panel["upazila_pcode"].nunique()},
        {"metric": "year_min", "value": int(panel["year"].min())},
        {"metric": "year_max", "value": int(panel["year"].max())},
        {"metric": "n_columns", "value": len(panel.columns)},
    ]
    if erosion_col:
        nat = panel.groupby("year")[erosion_col].sum()
        rows.append({"metric": "erosion_series", "value": erosion_col})
        rows.append({"metric": "national_mean_ha_yr_2000_2020", "value": round(nat.loc[2000:2020].mean(), 1)})

    pd.DataFrame(rows).to_csv(out_dir / "panel_quality_report.csv", index=False)
    print(f"Quality report → {out_dir.name}/panel_quality_report.csv")
    print(f"Missingness → {out_dir.name}/panel_missingness_pct.csv")


if __name__ == "__main__":
    main()
