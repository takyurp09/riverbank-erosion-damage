# Google Earth Engine Workflow

This repository uses Google Earth Engine (GEE) as the cloud-processing layer for large-scale remote-sensing inputs. The scripts in `scripts/gee/` are designed to export analysis-ready layers that are later processed locally in Python.

## Why GEE Is Used

Riverbank erosion analysis requires repeated spatial operations over many years of satellite imagery. GEE is useful because it allows:

- cloud-based access to Landsat and Sentinel-2 archives
- annual and seasonal compositing without local image downloads
- large-scale raster masking and zonal export
- repeatable scripts for population, built environment, cropland, water, and climate layers
- export of standardized intermediate products for downstream geospatial analysis

## GEE Script Inventory

| Script | Main GEE Products | Purpose | Downstream Use |
|---|---|---|---|
| `check_auth.py` | Earth Engine account/project | Verify authentication and project access | Setup check |
| `jrc_gsw_export.py` | JRC Global Surface Water | Export yearly water-history layers | Baseline erosion detection |
| `jrc_gsw_gain_export.py` | JRC Global Surface Water transition/gain layers | Export water gain/change layers | Robustness and validation |
| `landsat_erosion_export.py` | Landsat 5/7/8/9 | Build annual dry-season water masks | Main erosion detection |
| `sentinel2_erosion_export.py` | Sentinel-2 MSI | Higher-resolution erosion checks | Sensor robustness |
| `worldpop_export.py` | WorldPop | Export annual population exposure layers | Displacement exposure |
| `ghsl_export.py` | GHSL | Export built-up/population grids | Cross-validation and pre-period support |
| `open_buildings_export.py` | Google Open Buildings | Export building footprint exposure | Structure-loss accounting |
| `ntl_export.py` | VIIRS/DMSP night lights | Export nighttime-light proxies | Land-value proxy |
| `cropland_export.py` | Cropland/land-cover products | Export cropland exposure layers | Agricultural-flow sensitivity |
| `chirps_export.py` | CHIRPS precipitation | Export rainfall anomalies | Hydroclimatic controls |
| `spei_export.py` | SPEI drought products | Export drought indices | Driver regression controls |
| `gmw_mangrove_export.py` | Global Mangrove Watch | Export mangrove exposure layers | Ecosystem-service accounting |

## Scale of Processing

The workflow is structured for repeated exports across:

- multiple satellite products
- annual time steps
- administrative units
- river reaches
- exposure layers
- robustness definitions

For a typical case study, the GEE stage can produce annual layers for physical erosion, population exposure, built-area exposure, cropland exposure, and hydroclimatic controls. These are then harmonized into an administrative-unit by year panel.

## Export Design

The GEE scripts follow a common pattern:

1. define the region of interest
2. load a provider-hosted image collection
3. filter by date and cloud/quality criteria
4. construct an annual or seasonal composite
5. compute the relevant index or mask
6. reduce or export to a standard spatial grid
7. write export-ready files for local Python processing

## Local Processing After GEE

The exported products are processed by scripts in `scripts/data_prep/`, especially:

- `process_gee_exports.py`
- `process_jrc_erosion.py`
- `compute_net_erosion.py`
- `assign_river_reach.py`
- `build_panel.py`
- `panel_quality_report.py`

This separation keeps cloud processing and local panel construction cleanly separated in version control.

## Public Repository Boundary

The repository commits GEE scripts and workflow documentation, but not exported rasters or generated panels. This keeps the GitHub repository lightweight and reproducible while avoiding raw-data uploads.
