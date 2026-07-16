# Data Availability

This repository does not include raw or processed geospatial data. Many inputs are large satellite products, provider-hosted rasters, or derived outputs that should not be stored directly in Git.

## Main Data Families

- Landsat surface reflectance and JRC Global Surface Water products for erosion detection
- Sentinel-2 imagery for high-resolution robustness checks
- Google Earth Engine exports for water, population, cropland, night lights, and environmental layers
- WorldPop and GHSL population grids
- Google Open Buildings and OpenStreetMap infrastructure layers
- SoilGrids, Global Mangrove Watch, and related ecosystem-service inputs
- ERA5, CHIRPS, GloFAS, SPEI, and ISIMIP hydroclimatic drivers
- Administrative boundaries and river-reach layers
- Public price, cost, and valuation parameters used in economic-damage accounting

## Expected Local Structure

Users adapting this workflow should keep data outside version control and use a local structure such as:

```text
data/
├── raw/
├── interim/
├── processed/
└── external/
```

The `.gitignore` file excludes common raster, vector, tabular, and generated-output formats.

## Public-Release Principle

Commit code, documentation, configuration templates, and selected public figures. Do not commit raw rasters, shapefiles, generated panels, private notes, manuscript drafts, or full unpublished result tables.
