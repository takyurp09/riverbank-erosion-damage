#!/usr/bin/env python3
"""Compute net erosion (gross loss − accretion) from JRC river-masked loss + gain panels."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def two_year_persistence(df: pd.DataFrame, value_col: str, out_col: str) -> pd.DataFrame:
    pivot = df.pivot(index="upazila_pcode", columns="year", values=value_col).fillna(0)
    years = sorted(df["year"].unique())
    rows = []
    for y in years:
        if y + 1 not in years:
            continue
        persistent = (pivot[y] > 0) & (pivot[y + 1] > 0)
        for pcode, val in persistent.items():
            if val:
                ha = min(pivot.loc[pcode, y], pivot.loc[pcode, y + 1])
                rows.append({"upazila_pcode": pcode, "year": y, out_col: ha})
    if not rows:
        return df.assign(**{out_col: 0.0})
    return df.merge(pd.DataFrame(rows), on=["upazila_pcode", "year"], how="left").assign(
        **{out_col: lambda d: d[out_col].fillna(0)}
    )


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    erosion_dir = ROOT / cfg["paths"]["processed_erosion"]
    loss_path = erosion_dir / "jrc_erosion_river_upazila_year.parquet"
    gain_path = erosion_dir / "jrc_gain_river_upazila_year.parquet"

    if not loss_path.exists():
        panel_path = ROOT / "data/processed/panel/panel_upazila_year.parquet"
        if panel_path.exists():
            panel = pd.read_parquet(panel_path)
            cols = ["upazila_pcode", "district_pcode", "upazila_name", "year", "erosion_gross_ha_1yr_river", "erosion_gross_ha_2yr_river"]
            if "erosion_gross_ha_1yr_river" in panel.columns:
                panel[cols].drop_duplicates(["upazila_pcode", "year"]).to_parquet(loss_path, index=False)
                print(f"Created {loss_path.name} from panel")
        if not loss_path.exists():
            print(f"Missing {loss_path.name} — process JRC loss exports first")
            return
    if not gain_path.exists():
        print(f"Missing {gain_path.name} — download JRC gain GEE exports to data/raw/ and run process_gee_exports.py")
        return

    loss = pd.read_parquet(loss_path)
    gain = pd.read_parquet(gain_path)

    net = loss.merge(
        gain[["upazila_pcode", "year", "accretion_gross_ha_1yr", "accretion_gross_ha_2yr"]],
        on=["upazila_pcode", "year"],
        how="outer",
    )
    for c in ["erosion_gross_ha_1yr_river", "erosion_gross_ha_2yr_river", "accretion_gross_ha_1yr", "accretion_gross_ha_2yr"]:
        if c in net.columns:
            net[c] = net[c].fillna(0)

    net["erosion_net_ha_1yr"] = (net["erosion_gross_ha_1yr_river"] - net["accretion_gross_ha_1yr"]).clip(lower=0)
    net["erosion_net_ha_2yr"] = (net["erosion_gross_ha_2yr_river"] - net["accretion_gross_ha_2yr"]).clip(lower=0)
    # Gain GEE exports are 5-yr snapshots (no consecutive-year pairs for 2yr persistence).
    # At snapshot years, approximate 2yr net using same-year 1yr accretion.
    snap = net["accretion_gross_ha_1yr"] > 0
    net.loc[snap, "erosion_net_ha_2yr"] = (
        net.loc[snap, "erosion_gross_ha_2yr_river"] - net.loc[snap, "accretion_gross_ha_1yr"]
    ).clip(lower=0)

    out = erosion_dir / "jrc_net_erosion_river_upazila_year.parquet"
    net.to_parquet(out, index=False)

    summary = net.groupby("year").agg(
        gross_1yr=("erosion_gross_ha_1yr_river", "sum"),
        accretion_1yr=("accretion_gross_ha_1yr", "sum"),
        net_1yr=("erosion_net_ha_1yr", "sum"),
        gross_2yr=("erosion_gross_ha_2yr_river", "sum"),
        accretion_2yr=("accretion_gross_ha_2yr", "sum"),
        net_2yr=("erosion_net_ha_2yr", "sum"),
    )
    summary.to_csv(ROOT / "output/tables/jrc_net_erosion_national.csv")

    # Merge into panel
    panel_path = ROOT / "data/processed/panel/panel_upazila_year.parquet"
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
        panel = panel.drop(
            columns=[c for c in panel.columns if c.startswith(("erosion_net_ha", "accretion_gross_ha"))],
            errors="ignore",
        )
        panel = panel.merge(
            net[
                [
                    "upazila_pcode",
                    "year",
                    "accretion_gross_ha_1yr",
                    "accretion_gross_ha_2yr",
                    "erosion_net_ha_1yr",
                    "erosion_net_ha_2yr",
                ]
            ],
            on=["upazila_pcode", "year"],
            how="left",
        )
        panel.to_parquet(panel_path, index=False)
        print(f"Merged net erosion into panel ({len(panel)} rows)")

    print(f"Net erosion → {out.name}")
    print(f"National summary → output/tables/jrc_net_erosion_national.csv")


if __name__ == "__main__":
    main()
