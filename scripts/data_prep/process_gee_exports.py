#!/usr/bin/env python3
"""Process GEE Drive CSV zips from data/raw → processed parquet; delete raw."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def year_from_path(path: str) -> int | None:
    m = re.search(r"(\d{4})", Path(path).stem)
    return int(m.group(1)) if m else None


def read_zip_csvs(zip_path: Path) -> pd.DataFrame:
    frames = []
    seen: set[str] = set()

    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if not name.endswith(".csv"):
                continue
            base = name.split("/")[-1]
            if base in seen:
                continue
            seen.add(base)
            df = pd.read_csv(zf.open(name))
            year = year_from_path(name)
            if year is not None and "year" not in df.columns:
                df["year"] = year
            if "year" in df.columns:
                df["year"] = df["year"].astype(int)
            frames.append(df)

    if not frames:
        raise ValueError(f"No CSV data in {zip_path}")
    return pd.concat(frames, ignore_index=True)


def standardize_geo(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    if "adm3_pcode" in df.columns:
        rename["adm3_pcode"] = "upazila_pcode"
    if "adm2_pcode" in df.columns:
        rename["adm2_pcode"] = "district_pcode"
    if "adm3_name" in df.columns:
        rename["adm3_name"] = "upazila_name"
    df = df.rename(columns=rename)
    drop = [c for c in df.columns if c in (".geo", "system:index")]
    return df.drop(columns=[c for c in drop if c in df.columns], errors="ignore")


def process_landsat(df: pd.DataFrame, out_path: Path, value_col: str) -> pd.DataFrame:
    df = standardize_geo(df)
    panel = df[["upazila_pcode", "district_pcode", "upazila_name", "year", "loss_ha"]].copy()
    panel = panel.rename(columns={"loss_ha": value_col})
    panel = panel.drop_duplicates(["upazila_pcode", "year"])
    panel.to_parquet(out_path, index=False)
    return panel


def process_jrc(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    panel = df[["upazila_pcode", "district_pcode", "upazila_name", "year", "loss_ha"]].copy()
    panel = panel.rename(columns={"loss_ha": "erosion_gross_ha_1yr_river"})
    panel = panel.drop_duplicates(["upazila_pcode", "year"])

    # Merge with existing data when processing partial GEE downloads
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = pd.concat([existing, panel], ignore_index=True)
        panel = panel.drop_duplicates(["upazila_pcode", "year"], keep="last")

    # Recompute 2yr persistence across full year range
    pivot = panel.pivot(index="upazila_pcode", columns="year", values="erosion_gross_ha_1yr_river").fillna(0)
    years = sorted(panel["year"].unique())
    persist_rows = []
    for y in years:
        if y + 1 not in years:
            continue
        persistent = (pivot[y] > 0) & (pivot[y + 1] > 0)
        for pcode, val in persistent.items():
            if val:
                ha = min(pivot.loc[pcode, y], pivot.loc[pcode, y + 1])
                persist_rows.append({"upazila_pcode": pcode, "year": y, "erosion_gross_ha_2yr_river": ha})

    panel = panel.drop(columns=["erosion_gross_ha_2yr_river"], errors="ignore")
    if persist_rows:
        panel = panel.merge(pd.DataFrame(persist_rows), on=["upazila_pcode", "year"], how="left")
        panel["erosion_gross_ha_2yr_river"] = panel["erosion_gross_ha_2yr_river"].fillna(0)
    else:
        panel["erosion_gross_ha_2yr_river"] = 0.0

    panel.to_parquet(out_path, index=False)
    return panel


def process_jrc_gain(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val = "gain_ha" if "gain_ha" in df.columns else "loss_ha"
    panel = df[["upazila_pcode", "district_pcode", "upazila_name", "year", val]].copy()
    panel = panel.rename(columns={val: "accretion_gross_ha_1yr"})
    panel = panel.drop_duplicates(["upazila_pcode", "year"])

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = pd.concat([existing, panel], ignore_index=True)
        panel = panel.drop_duplicates(["upazila_pcode", "year"], keep="last")

    pivot = panel.pivot(index="upazila_pcode", columns="year", values="accretion_gross_ha_1yr").fillna(0)
    years = sorted(panel["year"].unique())
    persist_rows = []
    for y in years:
        if y + 1 not in years:
            continue
        persistent = (pivot[y] > 0) & (pivot[y + 1] > 0)
        for pcode, val in persistent.items():
            if val:
                ha = min(pivot.loc[pcode, y], pivot.loc[pcode, y + 1])
                persist_rows.append({"upazila_pcode": pcode, "year": y, "accretion_gross_ha_2yr": ha})

    panel = panel.drop(columns=["accretion_gross_ha_2yr"], errors="ignore")
    if persist_rows:
        panel = panel.merge(pd.DataFrame(persist_rows), on=["upazila_pcode", "year"], how="left")
        panel["accretion_gross_ha_2yr"] = panel["accretion_gross_ha_2yr"].fillna(0)
    else:
        panel["accretion_gross_ha_2yr"] = 0.0

    panel.to_parquet(out_path, index=False)
    return panel


def process_mangrove(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    # GEE CSV may include both `mean` (fraction) and `mangrove_frac` (property copy); prefer reducer output
    if "mean" in df.columns:
        frac = df["mean"]
    elif "mangrove_frac" in df.columns:
        frac = df["mangrove_frac"]
    else:
        raise ValueError("No mangrove fraction column in GMW export")
    panel = df[["upazila_pcode", "year"]].copy()
    panel["mangrove_frac"] = pd.to_numeric(frac, errors="coerce")
    if panel["mangrove_frac"].max(skipna=True) > 1:
        panel["mangrove_frac"] = panel["mangrove_frac"] / 255.0
    panel["mangrove_frac"] = panel["mangrove_frac"].clip(0, 1)
    panel = panel.dropna(subset=["mangrove_frac"]).drop_duplicates(["upazila_pcode", "year"])

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = pd.concat([existing, panel], ignore_index=True)
        panel = panel.drop_duplicates(["upazila_pcode", "year"], keep="last")
    panel.to_parquet(out_path, index=False)
    return panel


def process_s2(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    return process_landsat(df, out_path, "erosion_gross_ha_2yr_s2_river")


def process_spei(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val_col = "spei3_mean" if "spei3_mean" in df.columns else "mean"
    panel = df[["upazila_pcode", "year", val_col]].copy()
    panel = panel.rename(columns={val_col: "spei3_mean"}).drop_duplicates(["upazila_pcode", "year"])
    panel.to_parquet(out_path, index=False)
    return panel


def process_chirps(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val_col = "precip_mm" if "precip_mm" in df.columns else "mean"
    panel = df[["upazila_pcode", "year", val_col]].copy()
    panel = panel.rename(columns={val_col: "precip_mm"}).drop_duplicates(["upazila_pcode", "year"])
    baseline = (
        panel[panel["year"].between(1990, 2020)]
        .groupby("upazila_pcode")["precip_mm"]
        .mean()
        .rename("precip_baseline_mm")
    )
    panel = panel.merge(baseline, on="upazila_pcode", how="left")
    panel["precip_anomaly_pct"] = (panel["precip_mm"] - panel["precip_baseline_mm"]) / panel["precip_baseline_mm"] * 100
    panel.to_parquet(out_path, index=False)
    return panel


def process_worldpop(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    cols = ["upazila_pcode", "year", "pop_total", "pop_density_km2"]
    panel = df[[c for c in cols if c in df.columns]].copy().drop_duplicates(["upazila_pcode", "year"])
    panel.to_parquet(out_path, index=False)
    return panel


def process_cropland(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val_col = "cropland" if "cropland" in df.columns else "mean"
    if "source" not in df.columns:
        df["source"] = "unknown"

    pieces = []
    for source, g in df.groupby("source"):
        col_name = f"cropland_frac_{source}"
        part = g[["upazila_pcode", "year", val_col]].rename(columns={val_col: col_name})
        part = part.drop_duplicates(["upazila_pcode", "year"])
        pieces.append(part)

    panel = pieces[0]
    for part in pieces[1:]:
        panel = panel.merge(part, on=["upazila_pcode", "year"], how="outer")

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = existing.merge(panel, on=["upazila_pcode", "year"], how="outer")

    panel = panel.sort_values(["upazila_pcode", "year"]).reset_index(drop=True)
    panel.to_parquet(out_path, index=False)
    return panel


def process_buildings(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    if "n_buildings" not in df.columns and "bldg_sum" in df.columns:
        df["n_buildings"] = df["bldg_sum"]
    if "footprint_m2" not in df.columns and "footprint_m2_sum" in df.columns:
        df["footprint_m2"] = df["footprint_m2_sum"]
    cols = ["upazila_pcode", "n_buildings", "footprint_m2"]
    panel = df[[c for c in cols if c in df.columns]].copy()
    panel = panel.drop_duplicates(["upazila_pcode"], keep="last")
    panel.to_parquet(out_path, index=False)
    return panel


def process_ntl(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val_col = "ntl_mean" if "ntl_mean" in df.columns else "mean"
    panel = df[["upazila_pcode", "year", val_col]].copy()
    panel = panel.rename(columns={val_col: "ntl_mean"}).drop_duplicates(["upazila_pcode", "year"])

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = pd.concat([existing, panel], ignore_index=True)
        panel = panel.drop_duplicates(["upazila_pcode", "year"], keep="last")
    panel.to_parquet(out_path, index=False)
    return panel


def process_ghsl(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df = standardize_geo(df)
    val_col = "ghsl_pop" if "ghsl_pop" in df.columns else "sum"
    panel = df[["upazila_pcode", "year", val_col]].copy()
    panel = panel.rename(columns={val_col: "ghsl_pop"}).drop_duplicates(["upazila_pcode", "year"])

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        panel = pd.concat([existing, panel], ignore_index=True)
        panel = panel.drop_duplicates(["upazila_pcode", "year"], keep="last")
    panel.to_parquet(out_path, index=False)
    return panel


def detect_layer(zip_name: str) -> str | None:
    order = [
        ("jrc_gain", "jrc_gain"),
        ("s2_river", "s2_river"),
        ("gmw", "gmw"),
        ("mangrove", "gmw"),
        ("landsat_river", "landsat_river"),
        ("jrc_river", "jrc_river"),
        ("landsat", "landsat"),
        ("worldpop", "worldpop"),
        ("cropland", "cropland"),
        ("buildings", "buildings"),
        ("ntl", "ntl"),
        ("ghsl", "ghsl"),
        ("chirps", "chirps"),
        ("spei", "spei"),
        ("jrc", "jrc"),
    ]
    for key, label in order:
        if key in zip_name:
            return label
    return None


def process_all(raw_dir: Path, cfg: dict) -> dict:
    results = {}
    erosion_dir = ROOT / cfg["paths"]["processed_erosion"]
    climate_dir = ROOT / cfg["paths"]["processed_climate"]
    pop_dir = ROOT / cfg["paths"]["processed_population"]
    land_dir = ROOT / "data/processed/landuse"
    infra_dir = ROOT / cfg["paths"]["processed_infrastructure"]
    land_dir.mkdir(parents=True, exist_ok=True)
    infra_dir.mkdir(parents=True, exist_ok=True)

    eco_dir = ROOT / cfg["paths"]["processed_ecosystem"]
    eco_dir.mkdir(parents=True, exist_ok=True)

    handlers = {
        "jrc_gain": lambda df: process_jrc_gain(df, erosion_dir / "jrc_gain_river_upazila_year.parquet"),
        "s2_river": lambda df: process_s2(df, erosion_dir / "s2_erosion_2yr_river_upazila_year.parquet"),
        "gmw": lambda df: process_mangrove(df, eco_dir / "gmw_mangrove_frac_upazila_year.parquet"),
        "landsat_river": lambda df: process_landsat(
            df, erosion_dir / "landsat_erosion_2yr_river_upazila_year.parquet", "erosion_gross_ha_2yr_river_landsat"
        ),
        "landsat": lambda df: process_landsat(
            df, erosion_dir / "landsat_erosion_2yr_upazila_year.parquet", "erosion_gross_ha_2yr_landsat"
        ),
        "jrc_river": lambda df: process_jrc(df, erosion_dir / "jrc_erosion_river_upazila_year.parquet"),
        "jrc": lambda df: process_jrc(df, erosion_dir / "jrc_erosion_river_upazila_year.parquet"),
        "spei": lambda df: process_spei(df, climate_dir / "spei3_upazila_year.parquet"),
        "chirps": lambda df: process_chirps(df, climate_dir / "chirps_upazila_year.parquet"),
        "worldpop": lambda df: process_worldpop(df, pop_dir / "worldpop_upazila_year.parquet"),
        "cropland": lambda df: process_cropland(df, land_dir / "cropland_upazila_year.parquet"),
        "buildings": lambda df: process_buildings(df, infra_dir / "open_buildings_upazila.parquet"),
        "ntl": lambda df: process_ntl(df, infra_dir / "ntl_viirs_upazila_year.parquet"),
        "ghsl": lambda df: process_ghsl(df, pop_dir / "ghsl_pop_upazila_year.parquet"),
    }

    for zip_path in sorted(raw_dir.glob("riverbank_erosion_*.zip")):
        layer = detect_layer(zip_path.name)
        if layer is None or layer not in handlers:
            print(f"Skipping unknown zip: {zip_path.name}")
            continue

        erosion_dir.mkdir(parents=True, exist_ok=True)
        climate_dir.mkdir(parents=True, exist_ok=True)
        pop_dir.mkdir(parents=True, exist_ok=True)

        df = read_zip_csvs(zip_path)
        panel = handlers[layer](df)
        results[layer] = len(panel)
        new_years = sorted(df["year"].unique()) if "year" in df.columns else []
        print(f"{layer}: {len(panel)} total rows (this zip: {len(df)} rows, years {new_years})")
        zip_path.unlink()
        print(f"  deleted {zip_path.name}")

    for d in raw_dir.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    return results


def main() -> None:
    cfg = load_config()
    raw_dir = ROOT / cfg["paths"]["raw"]
    results = process_all(raw_dir, cfg)
    print(f"Processed layers: {results}")
    remaining = list(raw_dir.iterdir())
    print(f"data/raw remaining: {[p.name for p in remaining] or '(empty)'}")


if __name__ == "__main__":
    main()
