#!/usr/bin/env python3
"""Week 6: SoilGrids ocs (soil organic carbon stock) at upazila centroids via REST API."""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
API = "https://rest.isric.org/soilgrids/v2.0/properties/query"


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def query_ocs(lon: float, lat: float) -> float | None:
    params = {
        "lon": lon,
        "lat": lat,
        "property": "ocs",
        "depth": "0-30cm",
        "value": "mean",
    }
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            layers = r.json()["properties"]["layers"]
            val = layers[0]["depths"][0]["values"]["mean"]
            return float(val) if val is not None else None
        except Exception:
            time.sleep(1)
    return None


def main() -> None:
    cfg = load_config()
    out_dir = ROOT / "data/processed/ecosystem"
    out_dir.mkdir(parents=True, exist_ok=True)

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["crs"])
    upazila["centroid"] = upazila.geometry.representative_point()

    out_path = out_dir / "soilgrids_ocs_upazila.parquet"
    cached: dict[str, float | None] = {}
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        for _, r in existing.iterrows():
            if pd.notna(r["ocs_t_ha"]):
                cached[str(r["upazila_pcode"])] = float(r["ocs_t_ha"])

    n = len(upazila)
    for i, (_, row) in enumerate(upazila.iterrows(), 1):
        pcode = str(row["adm3_pcode"])
        if pcode in cached:
            continue
        lon, lat = row["centroid"].x, row["centroid"].y
        cached[pcode] = query_ocs(lon, lat)
        if i % 50 == 0 or i == n:
            print(f"SoilGrids progress: {i}/{n} ({len(cached)} cached)", flush=True)
            _save_all(upazila, cached, out_path)
        time.sleep(0.15)

    df = _save_all(upazila, cached, out_path)
    print(f"Saved {len(df)} upazila ocs values → {out_dir.name}/soilgrids_ocs_upazila.parquet")
    print(f"Non-null: {df['ocs_t_ha'].notna().sum()}/{len(df)}")


def _save_all(upazila: gpd.GeoDataFrame, cached: dict[str, float | None], out_path: Path) -> pd.DataFrame:
    rows = [{"upazila_pcode": r["adm3_pcode"], "ocs_t_ha": cached.get(str(r["adm3_pcode"]))} for _, r in upazila.iterrows()]
    df = pd.DataFrame(rows)
    df.to_parquet(out_path, index=False)
    return df


if __name__ == "__main__":
    main()
