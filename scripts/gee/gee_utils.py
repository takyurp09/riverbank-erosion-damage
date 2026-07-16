"""Shared GEE helpers: upazila FC and HydroRIVERS river buffer mask."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[2]
BUFFER_CACHE = ROOT / "data/processed/hydrology/river_buffer_5km.gpkg"
COASTAL_BUFFER_CACHE = ROOT / "data/processed/hydrology/coastal_buffer_10km.gpkg"

COASTAL_DISTRICT_PCODES = {
    "BD1009",  # Bhola
    "BD2051",  # Lakshmipur
    "BD2013",  # Chandpur
    "BD2053",  # Noakhali
    "BD2015",  # Feni
    "BD2079",  # Patuakhali
    "BD2004",  # Barguna
    "BD2006",  # Barishal
    "BD2055",  # Pirojpur
    "BD2043",  # Jhalokati
}


def load_config() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


def load_upazila_fc(cfg: dict):
    import ee

    gdf = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    gdf = gdf[["adm3_pcode", "adm3_name", "adm2_pcode", "geometry"]].to_crs(cfg["project"]["crs"])
    gdf["geometry"] = gdf.geometry.simplify(0.001, preserve_topology=True)
    return ee.FeatureCollection(gdf.__geo_interface__)


def build_river_buffer_gpkg(cfg: dict) -> Path:
    """Pre-compute dissolved 5 km river buffer in UTM, save once locally."""
    if BUFFER_CACHE.exists():
        return BUFFER_CACHE

    min_dis = cfg["gee"].get("river_min_discharge_cms", 50)
    buffer_m = cfg["gee"].get("river_buffer_m", 5000)
    study_crs = cfg["project"]["study_crs"]

    rivers = gpd.read_file(ROOT / cfg["paths"]["processed_hydro"] / "hydrorivers_bgd.gpkg")
    rivers = rivers[rivers["DIS_AV_CMS"] >= min_dis].copy()
    rivers = rivers.to_crs(study_crs)
    rivers["geometry"] = rivers.geometry.simplify(500)  # 500 m tolerance in UTM

    dissolved = rivers.geometry.buffer(buffer_m).union_all()
    buf = gpd.GeoDataFrame({"name": ["river_buffer"]}, geometry=[dissolved], crs=study_crs)
    buf = buf.to_crs(cfg["project"]["crs"])
    BUFFER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    buf.to_file(BUFFER_CACHE, driver="GPKG")
    return BUFFER_CACHE


def build_coastal_buffer_gpkg(cfg: dict) -> Path | None:
    """10 km buffer around coastal-district upazilas for island/estuary erosion."""
    if COASTAL_BUFFER_CACHE.exists():
        return COASTAL_BUFFER_CACHE

    study_crs = cfg["project"]["study_crs"]
    coastal_m = cfg["gee"].get("coastal_buffer_m", 10000)
    upazila = gpd.read_file(ROOT / cfg["paths"]["processed_admin"] / "bgd_upazila.gpkg")
    coastal = upazila[upazila["adm2_pcode"].isin(COASTAL_DISTRICT_PCODES)].copy()
    if coastal.empty:
        return None
    coastal = coastal.to_crs(study_crs)
    dissolved = coastal.geometry.buffer(coastal_m).union_all()
    zone = gpd.GeoDataFrame({"name": ["coastal_buffer"]}, geometry=[dissolved], crs=study_crs)
    zone = zone.to_crs(cfg["project"]["crs"])
    COASTAL_BUFFER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    zone.to_file(COASTAL_BUFFER_CACHE, driver="GPKG")
    return COASTAL_BUFFER_CACHE


def erosion_zone_geometry(cfg: dict, aoi):
    """River buffer ∪ coastal buffer for GEE erosion masking."""
    import ee

    river_path = build_river_buffer_gpkg(cfg)
    river = gpd.read_file(river_path)
    geoms = [river.geometry.iloc[0]]

    coastal_path = build_coastal_buffer_gpkg(cfg)
    if coastal_path and coastal_path.exists():
        coastal = gpd.read_file(coastal_path)
        geoms.append(coastal.geometry.iloc[0])

    from shapely.ops import unary_union

    merged = unary_union(geoms)
    ee_geom = ee.Geometry(gpd.GeoSeries([merged], crs=cfg["project"]["crs"]).iloc[0].__geo_interface__)
    return ee_geom.intersection(aoi, ee.ErrorMargin(1))


def river_buffer_geometry(cfg: dict, aoi):
    """Single dissolved buffer polygon for GEE clipping."""
    import ee

    path = build_river_buffer_gpkg(cfg)
    buf = gpd.read_file(path)
    geom = buf.geometry.iloc[0].simplify(0.002, preserve_topology=True)
    ee_geom = ee.Geometry(geom.__geo_interface__)
    return ee_geom.intersection(aoi, ee.ErrorMargin(1))
