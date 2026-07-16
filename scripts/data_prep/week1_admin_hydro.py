#!/usr/bin/env python3
"""Week 1 data prep: HDX boundaries + HydroSHEDS rivers.

Downloads raw files to data/raw/, processes to clipped GeoPackages in
data/processed/, then deletes raw downloads and extracted folders.
"""

from __future__ import annotations

import logging
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import yaml
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "week1_admin_hydro.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)


def download_file(url: str, dest: Path, log: logging.Logger) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Already downloaded: %s", dest.name)
        return dest

    log.info("Downloading %s → %s", url, dest.name)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    log.info("Downloaded %.1f MB", dest.stat().st_size / 1e6)
    return dest


def extract_zip(zip_path: Path, extract_dir: Path, log: logging.Logger) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    log.info("Extracting %s", zip_path.name)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    return extract_dir


def find_shp(extract_dir: Path, pattern: str = "*.shp") -> Path:
    candidates = list(extract_dir.rglob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No shapefile matching {pattern} under {extract_dir}")
    return max(candidates, key=lambda p: p.stat().st_size)


def clip_bbox(gdf: gpd.GeoDataFrame, cfg: dict) -> gpd.GeoDataFrame:
    bb = cfg["bbox"]
    clip_box = box(
        bb["west"] - bb["buffer_deg"],
        bb["south"] - bb["buffer_deg"],
        bb["east"] + bb["buffer_deg"],
        bb["north"] + bb["buffer_deg"],
    )
    return gdf.clip(clip_box)


def process_boundaries(cfg: dict, raw_dir: Path, out_dir: Path, log: logging.Logger) -> None:
    dl = cfg["downloads"]["hdx_boundaries"]
    zip_path = raw_dir / dl["filename"]
    extract_dir = raw_dir / "hdx_boundaries"

    download_file(dl["url"], zip_path, log)
    extract_zip(zip_path, extract_dir, log)

    # HDX COD-AB ships separate polygon files per admin level (adm0–adm3).
    level_files = {
        "country": "bgd_admin0.geojson",
        "division": "bgd_admin1.geojson",
        "district": "bgd_admin2.geojson",
        "upazila": "bgd_admin3.geojson",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for level_name, filename in level_files.items():
        geojson_path = next(extract_dir.rglob(filename), None)
        if geojson_path is None:
            log.warning("Missing %s — skipping %s", filename, level_name)
            continue

        log.info("Reading %s", geojson_path.name)
        gdf = gpd.read_file(geojson_path)
        if gdf.crs is None:
            gdf = gdf.set_crs(cfg["project"]["crs"])
        else:
            gdf = gdf.to_crs(cfg["project"]["crs"])

        pcode_col = {
            "country": "adm0_pcode",
            "division": "adm1_pcode",
            "district": "adm2_pcode",
            "upazila": "adm3_pcode",
        }[level_name]

        if pcode_col in gdf.columns:
            gdf = gdf.drop_duplicates(subset=[pcode_col], keep="first")

        out_path = out_dir / f"bgd_{level_name}.gpkg"
        gdf.to_file(out_path, driver="GPKG")
        manifest_rows.append(
            {
                "layer": level_name,
                "n_features": len(gdf),
                "pcode_col": pcode_col,
                "path": str(out_path.relative_to(ROOT)),
            }
        )
        log.info("Wrote %s (%d features)", out_path.name, len(gdf))

    pd.DataFrame(manifest_rows).to_csv(out_dir / "admin_manifest.csv", index=False)

    shutil.rmtree(extract_dir, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    log.info("Removed raw HDX files")


def process_hydrorivers(cfg: dict, raw_dir: Path, out_dir: Path, log: logging.Logger) -> None:
    dl = cfg["downloads"]["hydrorivers_asia"]
    zip_path = raw_dir / dl["filename"]
    extract_dir = raw_dir / "hydrorivers_asia"

    download_file(dl["url"], zip_path, log)
    extract_zip(zip_path, extract_dir, log)

    shp_path = find_shp(extract_dir)
    log.info("Reading HydroRIVERS from %s", shp_path.name)
    rivers = gpd.read_file(shp_path)
    if rivers.crs is None:
        rivers = rivers.set_crs(cfg["project"]["crs"])
    else:
        rivers = rivers.to_crs(cfg["project"]["crs"])

    rivers_bgd = clip_bbox(rivers, cfg)
    keep_cols = [
        c
        for c in [
            "HYRIV_ID",
            "NEXT_DOWN",
            "MAIN_RIV",
            "LENGTH_KM",
            "DIST_SINK",
            "DIST_MAIN",
            "ENDO",
            "COAST",
            "ORDER",
            "SORT",
            "DIS_AV_CMS",
            "geometry",
        ]
        if c in rivers_bgd.columns
    ]
    rivers_bgd = rivers_bgd[keep_cols].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hydrorivers_bgd.gpkg"
    rivers_bgd.to_file(out_path, driver="GPKG")

    pd.DataFrame(
        [
            {
                "layer": "hydrorivers_bgd",
                "n_reaches": len(rivers_bgd),
                "total_length_km": float(rivers_bgd["LENGTH_KM"].sum()) if "LENGTH_KM" in rivers_bgd.columns else None,
                "path": str(out_path.relative_to(ROOT)),
            }
        ]
    ).to_csv(out_dir / "hydro_manifest.csv", index=False)

    log.info("Wrote %s (%d river reaches)", out_path.name, len(rivers_bgd))

    shutil.rmtree(extract_dir, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    log.info("Removed raw HydroRIVERS files")


def main() -> None:
    cfg = load_config()
    log = setup_logging(ROOT / cfg["paths"]["logs"])
    raw_dir = ROOT / cfg["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Week 1: admin boundaries + HydroRIVERS ===")
    process_boundaries(cfg, raw_dir, ROOT / cfg["paths"]["processed_admin"], log)
    process_hydrorivers(cfg, raw_dir, ROOT / cfg["paths"]["processed_hydro"], log)

    remaining = list(raw_dir.iterdir()) if raw_dir.exists() else []
    if remaining:
        log.warning("Raw dir still contains: %s", [p.name for p in remaining])
    else:
        log.info("data/raw/ is empty — raw downloads cleaned up")

    log.info("Week 1 local data prep complete.")


if __name__ == "__main__":
    main()
