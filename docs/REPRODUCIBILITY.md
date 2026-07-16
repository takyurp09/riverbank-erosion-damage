# Reproducibility and Version-Control Workflow

This repository is organized as a public, version-controlled geospatial research workflow. The goal is to make the structure and methods reviewable while keeping raw data and generated outputs outside Git.

## Suggested Run Order

1. Configure local paths and provider credentials.

```bash
earthengine authenticate
```

2. Run Google Earth Engine export scripts as needed.

```bash
python scripts/gee/check_auth.py
python scripts/gee/jrc_gsw_export.py
python scripts/gee/landsat_erosion_export.py
python scripts/gee/sentinel2_erosion_export.py
python scripts/gee/worldpop_export.py
python scripts/gee/open_buildings_export.py
python scripts/gee/ntl_export.py
```

3. Process exported geospatial layers.

```bash
python scripts/data_prep/process_gee_exports.py
python scripts/data_prep/process_jrc_erosion.py
python scripts/data_prep/compute_net_erosion.py
python scripts/data_prep/assign_river_reach.py
python scripts/data_prep/build_panel.py
python scripts/data_prep/panel_quality_report.py
```

4. Estimate damage components.

```bash
python scripts/data_prep/estimate_damage.py
python scripts/data_prep/process_spam.py
python scripts/data_prep/week7_osm_infrastructure.py
```

5. Run analysis.

```bash
python scripts/analysis/descriptive_summaries.py
python scripts/analysis/driver_regression.py
python scripts/analysis/heterogeneity_regression.py
python scripts/analysis/robustness_checks.py
python scripts/analysis/monte_carlo_damage.py
python scripts/analysis/ssp_scenario_accounting.py
python scripts/analysis/generate_figures.py
```

The exact run order may vary by case study and data availability.

## Version-Control Rules

Commit:

- scripts
- documentation
- requirements files
- configuration templates
- small selected public figures

Do not commit:

- raw satellite imagery
- raster exports
- shapefiles or GeoPackages
- generated panels
- logs and caches
- full result tables
- manuscript drafts
- credentials or API tokens

## Example Commit Practice

```bash
git status
git add scripts/ docs/ README.md
git commit -m "Add riverbank erosion damage workflow"
git push
```

Use descriptive commits that reveal the research workflow:

- `Add GEE erosion export scripts`
- `Document damage accounting workflow`
- `Add panel quality checks`
- `Add Monte Carlo uncertainty script`

## Public Portfolio Scope

The public repository is intended to demonstrate remote-sensing, geospatial processing, economic damage accounting, and reproducible coding practice. It is not a full public release of all data products or manuscript materials.
