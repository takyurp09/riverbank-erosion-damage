#!/usr/bin/env python3
"""Merge JRC GSW upazila CSV exports into erosion panel; delete raw."""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def find_jrc_zip(raw_dir: Path) -> Path:
    zips = sorted(raw_dir.glob("*jrc*.zip"))
    if not zips:
        raise FileNotFoundError(f"No JRC zip in {raw_dir}")
    return zips[-1]


def year_from_name(name: str) -> int | None:
    m = re.search(r"(\d{4})", name)
    return int(m.group(1)) if m else None


def process_jrc_zip(zip_path: Path, out_dir: Path) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = out_dir / "_tmp_jrc"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    frames = []
    seen_years: set[int] = set()
    for csv in sorted(extract_dir.rglob("*.csv")):
        year = year_from_name(csv.stem)
        if year is None or year in seen_years:
            continue
        seen_years.add(year)

        df = pd.read_csv(csv)
        keep = [c for c in ["adm3_pcode", "adm2_pcode", "adm3_name", "year", "loss_ha", "loss_pixels", "sum"] if c in df.columns]
        df = df[keep].copy()
        if "year" not in df.columns:
            df["year"] = year
        df["year"] = df["year"].astype(int)
        df = df.rename(columns={"adm3_pcode": "upazila_pcode", "adm2_pcode": "district_pcode", "adm3_name": "upazila_name"})
        df["erosion_gross_ha_1yr"] = df["loss_ha"]
        frames.append(df)

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.drop_duplicates(subset=["upazila_pcode", "year"], keep="first")
    panel = panel.sort_values(["year", "upazila_pcode"]).reset_index(drop=True)

    # Two-year persistence rule (main definition per data_plan)
    pivot = panel.pivot(index="upazila_pcode", columns="year", values="erosion_gross_ha_1yr").fillna(0)
    years = sorted(panel["year"].unique())
    persist_rows = []
    for y in years:
        if y + 1 not in years:
            continue
        persistent = (pivot[y] > 0) & (pivot[y + 1] > 0)
        for pcode, val in persistent.items():
            if val:
                ha = min(pivot.loc[pcode, y], pivot.loc[pcode, y + 1])
                persist_rows.append({"upazila_pcode": pcode, "year": y, "erosion_gross_ha_2yr": ha})

    if persist_rows:
        persist_df = pd.DataFrame(persist_rows)
        panel = panel.merge(persist_df, on=["upazila_pcode", "year"], how="left")
        panel["erosion_gross_ha_2yr"] = panel["erosion_gross_ha_2yr"].fillna(0)
    else:
        panel["erosion_gross_ha_2yr"] = 0.0

    out_parquet = out_dir / "jrc_erosion_upazila_year.parquet"
    out_csv = out_dir / "jrc_erosion_upazila_year.csv"
    panel.to_parquet(out_parquet, index=False)
    panel.to_csv(out_csv, index=False)

    summary = panel.groupby("year").agg(
        erosion_ha_1yr=("erosion_gross_ha_1yr", "sum"),
        erosion_ha_2yr=("erosion_gross_ha_2yr", "sum"),
        n_upazila_1yr=("erosion_gross_ha_1yr", lambda s: (s > 0).sum()),
    )
    summary.to_csv(out_dir / "jrc_erosion_national_summary.csv")

    shutil.rmtree(extract_dir, ignore_errors=True)
    zip_path.unlink(missing_ok=True)

    print(f"Panel: {len(panel)} rows, years {panel['year'].min()}–{panel['year'].max()}")
    print(f"Saved: {out_parquet.relative_to(ROOT)}")
    print(f"Deleted raw: {zip_path.name}")
    return panel


def main() -> None:
    cfg = load_config()
    raw_dir = ROOT / cfg["paths"]["raw"]
    out_dir = ROOT / "data/processed/erosion"
    zip_path = find_jrc_zip(raw_dir)
    process_jrc_zip(zip_path, out_dir)


if __name__ == "__main__":
    main()
