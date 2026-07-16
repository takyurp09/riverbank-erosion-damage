#!/usr/bin/env python3
"""Extrapolate WorldPop 2021–2024 from 2015–2020 upazila growth rates (data_plan main approach)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    wp = pd.read_parquet(ROOT / cfg["paths"]["processed_population"] / "worldpop_upazila_year.parquet")
    growth = (
        wp[wp["year"].between(2015, 2020)]
        .sort_values(["upazila_pcode", "year"])
        .groupby("upazila_pcode")
        .apply(lambda g: (g["pop_total"].iloc[-1] / g["pop_total"].iloc[0]) ** (1 / 5) - 1)
        .rename("growth_rate")
        .reset_index()
    )

    base = wp[wp["year"] == 2020][["upazila_pcode", "pop_total", "pop_density_km2"]].copy()
    extra_rows = []
    for y in range(2021, 2025):
        for _, row in base.iterrows():
            gr = growth.loc[growth["upazila_pcode"] == row["upazila_pcode"], "growth_rate"].iloc[0]
            years_fwd = y - 2020
            pop = row["pop_total"] * (1 + gr) ** years_fwd
            extra_rows.append(
                {
                    "upazila_pcode": row["upazila_pcode"],
                    "year": y,
                    "pop_total": pop,
                    "pop_density_km2": row["pop_density_km2"] * (1 + gr) ** years_fwd,
                    "pop_source": "worldpop_extrapolated",
                }
            )

    ext = pd.concat([wp.assign(pop_source="worldpop"), pd.DataFrame(extra_rows)], ignore_index=True)
    ext = ext.drop_duplicates(["upazila_pcode", "year"], keep="last")
    out = ROOT / cfg["paths"]["processed_population"] / "worldpop_upazila_year.parquet"
    ext.to_parquet(out, index=False)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    panel = panel.drop(columns=["pop_total", "pop_density_km2", "pop_source"], errors="ignore")
    panel = panel.merge(
        ext[["upazila_pcode", "year", "pop_total", "pop_density_km2", "pop_source"]],
        on=["upazila_pcode", "year"],
        how="left",
    )
    panel.to_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet", index=False)
    print(f"WorldPop extrapolated 2021–2024 → {len(extra_rows)} rows added")


if __name__ == "__main__":
    main()
