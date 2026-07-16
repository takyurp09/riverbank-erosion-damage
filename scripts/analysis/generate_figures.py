#!/usr/bin/env python3
"""Phase 3 figures: national erosion/damage time series and component stacks."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    out_dir = ROOT / "output/figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    nat = pd.read_csv(ROOT / "output/tables/national_damage_by_year.csv")
    ero = pd.read_csv(ROOT / "output/tables/national_erosion_damage_timeseries.csv")

    # Figure 1: erosion time series
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ero["year"], ero["erosion_ha_calibrated"] / 1000, color="#c0392b", lw=1.5)
    ax.set_xlabel("Year")
    ax.set_ylabel("National erosion (×1000 ha)")
    ax.set_title("Bangladesh riverbank erosion (calibrated, 1990–2023)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "fig01_national_erosion_timeseries.png", dpi=150)
    plt.close(fig)

    # Figure 2: stacked asset damage components
    cols = ["D_land_ntl_usd", "D_struct_usd", "D_displace_usd", "D_ecosys_usd"]
    sub = nat[nat["year"].between(1990, 2024)].copy()
    for c in cols:
        sub[c] = sub[c] / 1e6
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.stackplot(
        sub["year"],
        sub["D_land_ntl_usd"],
        sub["D_struct_usd"],
        sub["D_displace_usd"],
        sub["D_ecosys_usd"],
        labels=["Land (NTL)", "Structures", "Displacement", "Ecosystem"],
        alpha=0.85,
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Damage (USD millions)")
    ax.set_title("National asset-loss damage by component")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "fig02_damage_components_stacked.png", dpi=150)
    plt.close(fig)

    # Figure 3: D_land method bounds
    if "D_total_asset_npv_usd" in nat.columns:
        sub2 = nat[nat["year"].between(2000, 2020)].copy()
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(sub2["year"], sub2["D_total_asset_usd"] / 1e6, label="Total (NTL land)", lw=1.5)
        ax.plot(sub2["year"], sub2["D_total_asset_npv_usd"] / 1e6, label="Total (NPV land)", lw=1.5)
        ax.plot(sub2["year"], sub2["D_total_asset_transfer_usd"] / 1e6, label="Total (Transfer land)", lw=1.5)
        ax.set_xlabel("Year")
        ax.set_ylabel("USD millions")
        ax.set_title("Damage bounds by land valuation method")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "fig03_damage_land_method_bounds.png", dpi=150)
        plt.close(fig)

    # Figure 4: gross vs net erosion at snapshot years
    net_path = ROOT / "output/tables/jrc_net_erosion_national.csv"
    if net_path.exists():
        net = pd.read_csv(net_path)
        snap = net[net["year"].isin([1990, 1995, 2000, 2005, 2010, 2015, 2020])]
        if not snap.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(snap))
            w = 0.35
            ax.bar(x - w / 2, snap["gross_1yr"] / 1000, w, label="Gross loss", color="#c0392b")
            ax.bar(x + w / 2, snap["net_1yr"] / 1000, w, label="Net (loss − accretion)", color="#2980b9")
            ax.set_xticks(x)
            ax.set_xticklabels(snap["year"].astype(int))
            ax.set_xlabel("Year (JRC snapshot)")
            ax.set_ylabel("National erosion (×1000 ha)")
            ax.set_title("Gross vs net riverbank erosion (JRC gain snapshots)")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3, axis="y")
            fig.tight_layout()
            fig.savefig(out_dir / "fig04_gross_vs_net_erosion.png", dpi=150)
            plt.close(fig)

    print(f"Figures → {out_dir.name}/")

    # Figure 5: DSAS end-point rate by river system
    dsas_path = ROOT / "output/tables/dsas_epr_by_river_system.csv"
    if dsas_path.exists():
        dsas = pd.read_csv(dsas_path)
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(dsas["river_system"], dsas["mean_epr_m_yr"], color="#16a085")
        ax.set_ylabel("Mean EPR (m/yr)")
        ax.set_title("DSAS-style shoreline retreat rate by river system")
        ax.grid(alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(out_dir / "fig05_dsas_epr_by_system.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    main()
