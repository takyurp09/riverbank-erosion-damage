#!/usr/bin/env python3
"""Week 7: OSM embankment + road density per upazila from GeoFabrik extract."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
GEOFABRIK_URL = "https://download.geofabrik.de/asia/bangladesh-latest-free.shp.zip"


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def download_osm(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "bangladesh-latest-free.shp.zip"
    if not zip_path.exists():
        print("Downloading GeoFabrik Bangladesh OSM...")
        with requests.get(GEOFABRIK_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
    extract_dir = raw_dir / "osm_bgd"
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    zip_path.unlink(missing_ok=True)
    return extract_dir


def main() -> None:
    cfg = load_config()
    raw_dir = ROOT / cfg["paths"]["raw"] / "osm"
    out_dir = ROOT / "data/processed/infrastructure"
    out_dir.mkdir(parents=True, exist_ok=True)

    extract_dir = download_osm(raw_dir)
    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["study_crs"])

    # Roads
    roads_path = next(extract_dir.rglob("gis_osm_roads_free_1.shp"), None)
    roads_gdf = gpd.read_file(roads_path).to_crs(cfg["project"]["study_crs"]) if roads_path else None

    # Waterways (proxy for embankments — OSM embankment tag sparse; use man_made embankment if present)
    emb_path = list(extract_dir.rglob("*embankment*")) or list(extract_dir.rglob("gis_osm_waterways_free_1.shp"))
    emb_gdf = None
    for p in emb_path:
        if p.suffix == ".shp":
            emb_gdf = gpd.read_file(p).to_crs(cfg["project"]["study_crs"])
            break

    rows = []
    for _, u in upazila.iterrows():
        geom = u.geometry
        area_km2 = u.get("area_sqkm") or (geom.area / 1e6)
        road_km = 0.0
        emb_km = 0.0
        if roads_gdf is not None:
            clipped = roads_gdf[roads_gdf.intersects(geom)]
            if len(clipped):
                road_km = clipped.clip(geom).length.sum() / 1000
        if emb_gdf is not None:
            clipped = emb_gdf[emb_gdf.intersects(geom)]
            if len(clipped):
                emb_km = clipped.clip(geom).length.sum() / 1000
        rows.append(
            {
                "upazila_pcode": u["adm3_pcode"],
                "road_km": road_km,
                "road_density_km_km2": road_km / area_km2 if area_km2 else None,
                "embankment_km": emb_km,
            }
        )

    pd.DataFrame(rows).to_parquet(out_dir / "osm_infrastructure_upazila.parquet", index=False)
    shutil.rmtree(raw_dir, ignore_errors=True)
    print(f"Saved infrastructure → {out_dir.name}/osm_infrastructure_upazila.parquet")


if __name__ == "__main__":
    main()
