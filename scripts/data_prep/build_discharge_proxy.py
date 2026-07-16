#!/usr/bin/env python3
"""Interim discharge anomaly at reach level from CHIRPS precip (until GloFAS licence/download completes)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    assign = pd.read_csv(ROOT / cfg["paths"]["processed_hydro"] / "upazila_river_reach.csv")

    # Reach-year mean precip anomaly from member upazilas
    merged = assign.merge(
        panel[["upazila_pcode", "year", "precip_anomaly_pct"]],
        on="upazila_pcode",
        how="left",
    )
    reach_year = (
        merged.groupby(["main_river_flag", "year"])
        .agg(
            discharge_anomaly_pct=("precip_anomaly_pct", "mean"),
            discharge_cms=("reach_discharge_cms", "first"),
        )
        .reset_index()
        .rename(columns={"main_river_flag": "river_reach_id"})
    )

    out_dir = ROOT / cfg["paths"]["processed_hydro"]
    reach_year.to_parquet(out_dir / "discharge_anomaly_proxy_reach_year.parquet", index=False)

    upa = assign.merge(
        reach_year.rename(columns={"river_reach_id": "main_river_flag"}),
        on="main_river_flag",
        how="left",
    )
    upa_dis = upa.groupby(["upazila_pcode", "year"]).first().reset_index()

    panel = panel.drop(columns=["discharge_anomaly_pct", "discharge_cms"], errors="ignore")
    panel = panel.merge(
        upa_dis[["upazila_pcode", "year", "discharge_anomaly_pct", "discharge_cms"]],
        on=["upazila_pcode", "year"],
        how="left",
    )
    panel["discharge_source"] = "chirps_proxy"
    panel.to_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet", index=False)
    print(f"Interim discharge anomaly (CHIRPS proxy) → {len(reach_year)} reach-years, merged to panel")


if __name__ == "__main__":
    main()
