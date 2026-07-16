# Riverbank Erosion Damage Accounting

This repository contains a reproducible geospatial research pipeline for measuring riverbank erosion and translating observed land loss into economic damage accounts. The workflow combines satellite-derived erosion detection, administrative-unit aggregation, exposure layers, asset valuation, hydroclimatic drivers, and uncertainty analysis.

The repository is written as a generic methodological template. The included documentation uses Bangladesh as a case-study application, but the workflow is designed to be adapted to other river systems and delta regions.

## What This Repository Demonstrates

- Google Earth Engine workflows for Landsat, Sentinel-2, JRC Global Surface Water, CHIRPS, WorldPop, GHSL, night lights, and related layers
- Python geospatial processing with `geopandas`, `rasterio`, `xarray`, and `statsmodels`
- Satellite-based erosion detection and validation
- Administrative-unit panel construction
- Economic damage accounting for land, structures, displacement, and ecosystem services
- Robustness checks, driver regressions, scenario accounting, and Monte Carlo uncertainty
- Version-controlled project organization for collaborative research

## Research Workflow

```text
.
├── scripts/
│   ├── gee/          # Google Earth Engine export scripts
│   ├── data_prep/    # Geospatial processing and panel construction
│   └── analysis/     # Descriptive summaries, regressions, robustness, uncertainty
├── docs/             # Method notes and case-study documentation
├── data/             # Data note only; raw data are excluded
├── figures/selected/ # Small public-facing workflow visuals
├── requirements.txt
└── README.md
```

## Pipeline Stages

1. **Remote-sensing exports**  
   Use Google Earth Engine to export water, population, cropland, buildings, climate, and exposure layers.

2. **Erosion detection and harmonization**  
   Process JRC/Landsat/Sentinel-derived erosion layers, compute gross and net erosion, assign river reaches, and run face-validity checks.

3. **Exposure and damage accounting**  
   Combine erosion polygons or raster loss layers with land-value proxies, building footprints, population exposure, cropland, soil carbon, and ecosystem-service layers.

4. **Panel construction**  
   Build administrative-unit by year panels for erosion, damages, exposure, protection variables, and hydroclimatic drivers.

5. **Analysis and uncertainty**  
   Generate descriptive summaries, driver regressions, heterogeneity tests, robustness checks, scenario accounting, and Monte Carlo damage intervals.

## Selected Figures

The repository includes a small set of public-facing visuals in `figures/selected/` to make the public portfolio easy to scan:

- workflow overview
- conceptual damage-accounting framework
- gross versus net erosion diagnostic
- DSAS-style shoreline retreat diagnostic

Full generated maps, damage figures, and result tables are intentionally excluded unless explicitly curated for public release.

## Data

Raw data are not included. Several inputs are large geospatial rasters, external satellite products, or provider-hosted datasets. See `data/README.md` for data-source notes.

## Google Earth Engine at Scale

The GEE workflow is documented in `docs/GEE_WORKFLOW.md`, including the main Earth Engine products, export scripts, and downstream use of each exported layer.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Google Earth Engine scripts require a configured Earth Engine account and project:

```bash
earthengine authenticate
```

## Reproducibility

See `docs/REPRODUCIBILITY.md` for the suggested run order and version-control rules.

## Portfolio Scope

This is a public code-portfolio version of an active research workflow. It includes scripts and documentation that demonstrate the methods, but excludes raw data, generated panels, manuscript drafts, and full unpublished result tables.

## Suggested Repository Name

`riverbank-erosion-damage-accounting`

## Suggested Topics

`remote-sensing`, `google-earth-engine`, `riverbank-erosion`, `geospatial`, `damage-accounting`, `climate-risk`, `python`, `landsat`, `sentinel-2`, `reproducible-research`
