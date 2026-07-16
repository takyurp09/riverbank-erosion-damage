#!/usr/bin/env python3
"""Phase 7: Monte Carlo uncertainty on total asset damage (10k draws)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
N_SIM = 10_000


def load_params() -> dict:
    with open(ROOT / "config" / "damage_params.yaml") as f:
        return yaml.safe_load(f)


def main() -> None:
    params = load_params()
    panel = pd.read_parquet(ROOT / "data/processed/panel/panel_upazila_year.parquet")
    df = panel[panel["year"].between(2000, 2020)].copy()

    erosion = df["erosion_gross_ha_calibrated"].fillna(0).values
    share = df["erosion_share"].fillna(0).values
    footprint = df["footprint_m2"].fillna(0).values
    pop_d = df["pop_density_km2"].fillna(0).values
    ocs = df["ocs_t_ha"].fillna(0).values
    ntl = df["ntl_mean"].fillna(0).values
    mangrove_frac = df["mangrove_frac"].fillna(0).values if "mangrove_frac" in df.columns else np.zeros(len(df))

    pwd = params["pwd_usd_per_m2"]
    disp = params["displacement"]
    eco = params["ecosystem"]
    fishery = eco.get("fishery", {})
    mangrove_usd_ha = fishery.get("mangrove_usd_per_ha_yr", eco["mangrove_usd_per_ha_yr"])
    ntl_scale = params["land_ntl"]["usd_per_ntl_unit_ha"]

    rng = np.random.default_rng(42)
    yearly = []
    for y in range(2000, 2021):
        mask = df["year"].values == y
        if not mask.any():
            continue
        e = erosion[mask]
        sh = share[mask]
        fp = footprint[mask]
        pd_ = pop_d[mask]
        oc = ocs[mask]
        nt = ntl[mask]
        mf = mangrove_frac[mask]

        sims = []
        for _ in range(N_SIM):
            pwd_draw = rng.uniform(pwd["kachha"], pwd["pucca"])
            mig = rng.uniform(150, 300)
            scc = rng.uniform(15, 51)
            ntl_u = max(rng.normal(ntl_scale, ntl_scale * 0.25), 0)

            d_struct = (fp * sh * pwd_draw).sum()
            persons = pd_ * e / 100
            hh = persons / disp["household_size"]
            d_disp = (hh * (mig + disp["daily_wage_usd"] * 30 * disp["disruption_months"])).sum()
            co2e = e * oc * eco["co2e_per_t_c"]
            d_soil = (co2e * scc).sum()
            d_mangrove = (e * mf * mangrove_usd_ha).sum()
            d_land = (e * nt * ntl_u).sum()
            sims.append(d_struct + d_disp + d_soil + d_mangrove + d_land)

        sims = np.array(sims)

        yearly.append({
            "year": y,
            "mean_usd": sims.mean(),
            "p5_usd": np.percentile(sims, 5),
            "p95_usd": np.percentile(sims, 95),
            "n_draws": N_SIM,
        })

    out = ROOT / "output/tables"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(yearly).to_csv(out / "damage_monte_carlo_by_year.csv", index=False)

    all_years = pd.DataFrame(yearly)
    national = pd.DataFrame([{
        "period": "2000-2020",
        "mean_usd_yr": all_years["mean_usd"].mean(),
        "p5_usd_yr": all_years["p5_usd"].mean(),
        "p95_usd_yr": all_years["p95_usd"].mean(),
        "n_draws": N_SIM,
    }])
    national.to_csv(out / "damage_monte_carlo_national.csv", index=False)
    print(f"Monte Carlo ({N_SIM} draws × 21 years) → {out.name}/damage_monte_carlo_by_year.csv")


if __name__ == "__main__":
    main()
