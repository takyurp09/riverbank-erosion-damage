# Method Note

This repository implements a reusable workflow for estimating economic damages from riverbank erosion using satellite and secondary data.

## Core Question

How can observed riverbank erosion be converted into a spatially explicit administrative-unit panel of physical land loss and economic damages?

## Main Components

### 1. Erosion Detection

The workflow uses satellite-derived water and land-cover information to identify land-to-water transitions over time. Depending on data availability, erosion can be detected using:

- Landsat dry-season composites
- Sentinel-2 robustness checks
- JRC Global Surface Water YearlyHistory
- NDWI-based water classification
- persistence rules that distinguish durable erosion from temporary inundation

### 2. Spatial Aggregation

Detected erosion is aggregated to policy-relevant administrative units and, where useful, river reaches. The output is an administrative-unit by year panel.

### 3. Damage Accounting

The damage-accounting framework separates several channels:

- land-value loss
- structure exposure
- displacement exposure
- ecosystem-service loss
- annual-flow cropland sensitivity

These components should be reported separately where assumptions differ across valuation methods.

### 4. Hydroclimatic Drivers

The workflow can merge erosion panels with river discharge, precipitation, drought, and climate-projection variables to study whether erosion varies with hydrological shocks.

### 5. Robustness and Uncertainty

Suggested robustness checks include:

- one-year versus two-year persistence rules
- Landsat versus Sentinel-2 erosion maps
- gross versus net erosion
- alternative land-valuation methods
- alternative population products
- administrative-unit and river-reach clustering
- Monte Carlo uncertainty over unit-cost assumptions

## Case-Study Adaptation

The current scripts were developed for a South Asian river-delta application, but the structure is intentionally reusable. To adapt the workflow to another river system, replace:

- administrative boundaries
- river-reach definitions
- erosion-detection geometry
- valuation parameters
- local price/cost sources
- validation hotspots

## Public Repository Scope

This repository releases code and workflow documentation, not full data products or unpublished paper results.
