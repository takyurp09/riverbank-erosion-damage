#!/usr/bin/env python3
"""Process SPAM 2020 v2.2 GeoTIFF tiles → upazila crop production (tonnes)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
import yaml

ROOT = Path(__file__).resolve().parents[2]
CROPS_WANTED = {"RICE", "MAIZ", "WHEA", "SUGC", "JUTE"}
MIN_ZIP_BYTES = 1_000_000


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def find_zips(raw_dir: Path) -> list[Path]:
    zips = list(raw_dir.rglob("*.zip"))
    valid = []
    for z in zips:
        if z.stat().st_size < MIN_ZIP_BYTES:
            print(f"skip invalid zip ({z.stat().st_size} B): {z}")
            continue
        try:
            with zipfile.ZipFile(z) as zf:
                if not any(n.lower().endswith((".tif", ".tiff")) for n in zf.namelist()):
                    print(f"skip non-geotiff zip: {z}")
                    continue
        except zipfile.BadZipFile:
            print(f"skip corrupt zip: {z}")
            continue
        valid.append(z)
    return valid


def extract_crops(zips: list[Path], extract_dir: Path) -> list[Path]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if not name.lower().endswith((".tif", ".tiff")):
                    continue
                if not any(c in name.upper() for c in CROPS_WANTED):
                    continue
                out_path = extract_dir / Path(name).name
                if out_path.exists() and out_path.stat().st_size > 0:
                    continue
                with zf.open(name) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
    return list(extract_dir.glob("*.tif")) + list(extract_dir.glob("*.tiff"))


def crop_code(stem: str) -> str:
    parts = stem.upper().split("_")
    for c in CROPS_WANTED:
        if c in parts:
            return c
    return parts[-2] if len(parts) > 1 else stem


def zonal_production_tonnes(tif: Path, upazila: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    with rasterio.open(tif) as src:
        crop = crop_code(tif.stem)
        nodata = src.nodata
        for _, u in upazila.iterrows():
            try:
                out, _ = mask(src, [u.geometry], crop=True, nodata=nodata)
                vals = out[0].astype(float)
                if nodata is not None:
                    vals = vals[vals != nodata]
                vals = vals[~np.isnan(vals)]
                tonnes = float(np.nansum(vals)) if len(vals) else 0.0
            except Exception:
                tonnes = np.nan
            rows.append({"upazila_pcode": u["adm3_pcode"], "crop": crop, "production_t": tonnes})
    return pd.DataFrame(rows)


def main() -> None:
    cfg = load_config()
    raw_dir = ROOT / cfg["paths"]["raw"] / "spam"
    out_dir = ROOT / "data/processed/landuse"
    out_dir.mkdir(parents=True, exist_ok=True)

    tifs = list(raw_dir.glob("*.tif")) + list(raw_dir.glob("*.tiff"))
    if not tifs:
        zips = find_zips(raw_dir)
        if zips:
            tifs = extract_crops(zips, raw_dir / "_extracted")

    if not tifs:
        print(f"No valid SPAM data in {raw_dir}")
        print("Download spam2020V2r2_global_production.geotiff.zip (~80 MB) from Harvard Dataverse")
        print("https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/SWPENT")
        return

    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    upazila = upazila.to_crs(cfg["project"]["crs"])

    frames = [zonal_production_tonnes(tif, upazila) for tif in tifs]
    prod = pd.concat(frames, ignore_index=True)
    prod.to_parquet(out_dir / "spam_production_upazila_crop.parquet", index=False)

    total = prod.groupby("upazila_pcode", as_index=False)["production_t"].sum()
    total = total.rename(columns={"production_t": "spam_production_t"})
    rice = (
        prod[prod["crop"] == "RICE"]
        .groupby("upazila_pcode", as_index=False)["production_t"]
        .sum()
        .rename(columns={"production_t": "spam_rice_t"})
    )
    total = total.merge(rice, on="upazila_pcode", how="left")
    total["spam_rice_t"] = total["spam_rice_t"].fillna(0)
    total.to_parquet(out_dir / "spam_production_upazila.parquet", index=False)

    print(f"SPAM → {out_dir.name}/spam_production_upazila.parquet ({len(tifs)} crops, 507 upazilas)")


if __name__ == "__main__":
    main()
