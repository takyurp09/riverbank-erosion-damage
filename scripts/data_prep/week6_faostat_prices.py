#!/usr/bin/env python3
"""Bangladesh rice producer prices from FAOSTAT (API → bulk CSV fallback)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
API = "https://fenixservices.fao.org/faostat/api/v1/en/data/QP"
BULK_URL = "https://bulks-faostat.fao.org/production/Prices_E_All_Data_(Normalized).zip"

# Bangladesh, Rice, Producer Price (USD/tonne)
AREA_CODE = 16
ITEM_CODE = 27
ELEMENT_CODE = 5532


def fetch_api() -> pd.DataFrame | None:
    params = {
        "format": "json",
        "area": str(AREA_CODE),
        "item": str(ITEM_CODE),
        "element": str(ELEMENT_CODE),
        "year": ",".join(str(y) for y in range(1990, 2025)),
    }
    for _ in range(3):
        try:
            r = requests.get(API, params=params, timeout=90)
            if r.status_code in (521, 503):
                continue
            r.raise_for_status()
            rows = r.json().get("data", [])
            if not rows:
                return None
            df = pd.DataFrame(rows)[["Year", "Value", "Unit"]].rename(
                columns={"Year": "year", "Value": "rice_price_usd_tonne", "Unit": "unit"}
            )
            df["year"] = df["year"].astype(int)
            df["source"] = "faostat_api"
            return df.dropna(subset=["rice_price_usd_tonne"]).drop_duplicates("year")
        except requests.RequestException:
            continue
    return None


def download_bulk(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zpath = raw_dir / "Prices_E_All_Data_Normalized.zip"
    if not zpath.exists() or zpath.stat().st_size < 1_000_000:
        print(f"Downloading FAOSTAT bulk prices → {zpath.name}")
        r = requests.get(BULK_URL, timeout=300, stream=True)
        r.raise_for_status()
        with open(zpath, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
    return zpath


def fetch_bulk(raw_dir: Path) -> pd.DataFrame:
    zpath = download_bulk(raw_dir)
    rows = []
    with zipfile.ZipFile(zpath) as zf:
        with zf.open("Prices_E_All_Data_(Normalized).csv") as f:
            for chunk in pd.read_csv(f, encoding="latin-1", chunksize=500_000):
                m = (
                    (chunk["Area Code"] == AREA_CODE)
                    & (chunk["Item Code"] == ITEM_CODE)
                    & (chunk["Element Code"] == ELEMENT_CODE)
                )
                sub = chunk.loc[m, ["Year", "Value", "Unit"]]
                if len(sub):
                    rows.append(sub)
    if not rows:
        raise RuntimeError("No Bangladesh rice prices in FAOSTAT bulk file")
    df = pd.concat(rows, ignore_index=True).rename(
        columns={"Year": "year", "Value": "rice_price_usd_tonne", "Unit": "unit"}
    )
    df["year"] = df["year"].astype(int)
    df = df.dropna(subset=["rice_price_usd_tonne"]).drop_duplicates("year").sort_values("year")
    df["source"] = "faostat_bulk"
    return df


def fill_years(df: pd.DataFrame, year_start: int = 1990, year_end: int = 2024) -> pd.DataFrame:
    """Linear interpolate gaps; hold last value for trailing years."""
    idx = pd.Index(range(year_start, year_end + 1), name="year")
    s = df.set_index("year")["rice_price_usd_tonne"].reindex(idx)
    s = s.interpolate(method="linear").ffill().bfill()
    out = s.reset_index()
    out["unit"] = "USD/tonne"
    out["source"] = df["source"].iloc[0] + "_interpolated"
    return out


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)
    out_dir = ROOT / cfg["paths"]["processed_landuse"]
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = ROOT / cfg["paths"]["raw"] / "faostat"

    df = fetch_api()
    if df is None:
        print("FAOSTAT API unavailable — using bulk CSV download")
        df = fetch_bulk(raw_dir)
    else:
        print("FAOSTAT API OK")

    df = fill_years(df)
    df.to_parquet(out_dir / "faostat_rice_price_year.parquet", index=False)
    df.to_csv(out_dir / "faostat_rice_price_year.csv", index=False)
    print(f"Saved {len(df)} years ({df.year.min()}–{df.year.max()}) → faostat_rice_price_year.parquet")
    print(f"  2020 price: ${df.loc[df.year == 2020, 'rice_price_usd_tonne'].iloc[0]:.1f}/t")


if __name__ == "__main__":
    main()
