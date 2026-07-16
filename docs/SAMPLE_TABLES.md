# Sample Tables

The following examples are small real-data extracts from processed outputs. They document data structure and variable definitions without releasing raw geospatial data, full panels, or complete result tables.

## Erosion Panel Extract

| upazila_pcode | district_name | upazila_name | year | erosion_gross_ha_calibrated | erosion_share | river_reach_id | discharge_anomaly_pct | D_total_asset_usd |
|---|---|---|---:|---:|---:|---|---:|---:|
| BD10040009 | Barguna | Amtali | 1990 | 0.4605 | 0.000015 | 41118548 | 19.7693 | 23818.68 |
| BD10040019 | Barguna | Bamna | 1990 | 0.2634 | 0.000026 | 41103608 |  | 25089.18 |
| BD10040028 | Barguna | Barguna Sadar | 1990 | 1.5678 | 0.000042 | 41118548 | 19.7693 | 156869.04 |

## Damage Components by Year

| year | D_struct_usd | D_ecosys_usd | D_total_asset_usd | D_total_asset_transfer_usd | D_ag_flow_usd |
|---:|---:|---:|---:|---:|---:|
| 1990 | 138531614.18 | 8291206.96 | 146822821.14 | 151806992.86 | 1646841.09 |
| 1991 | 132310740.57 | 8273129.15 | 140583869.73 | 145484811.61 | 1624710.15 |
| 1992 | 292863695.85 | 16988979.23 | 309852675.08 | 320179639.35 | 3521625.89 |

## River-System Summary

| river_system | mean_erosion_ha_yr_calibrated | mean_damage_usd_yr | n_districts_matched |
|---|---:|---:|---:|
| Jamuna | 666.6158 | 44543824.73 | 5 |
| Padma | 387.8239 | 21987694.30 | 5 |
| Meghna | 416.7655 | 30316721.56 | 5 |

## DSAS Retreat Summary

| river_system | mean_epr_m_yr | median_epr_m_yr | n_upazilas |
|---|---:|---:|---:|
| Jamuna | 3.8468 | 2.6196 | 39 |
| Padma | 2.0007 | 1.9910 | 30 |
| Meghna | 12.2917 | 2.4483 | 28 |

## Interpretation

- `erosion_gross_ha_calibrated`: calibrated physical erosion measure in hectares.
- `erosion_share`: calibrated erosion divided by administrative-unit area.
- `D_total_asset_usd`: asset-loss damage account using the baseline accounting assumptions.
- `D_total_asset_transfer_usd`: alternative damage account using transfer-value assumptions.
- `mean_epr_m_yr`: mean endpoint-rate shoreline retreat metric from DSAS-style transects.
