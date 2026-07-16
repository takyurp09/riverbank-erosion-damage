#!/usr/bin/env python3
"""Verify Google Earth Engine auth and project access."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)

    project_id = cfg["gee"]["project_id"]
    email = cfg["gee"].get("email", "")

    try:
        import ee
    except ImportError:
        print("Install: pip install earthengine-api")
        sys.exit(1)

    cred_path = Path.home() / ".config" / "earthengine" / "credentials"
    if not cred_path.exists():
        print("No GEE credentials found.")
        print(f"Run: conda activate crop_env && earthengine authenticate --auth_mode=localhost")
        print(f"Sign in with: {email}")
        sys.exit(1)

    try:
        ee.Initialize(project=project_id)
        # Lightweight check — getAssetRoots fails on new empty projects
        ee.ImageCollection("JRC/GSW1_4/YearlyHistory").limit(1).size().getInfo()
        print(f"GEE OK — project: {project_id}")
    except Exception as exc:
        print(f"GEE init failed: {exc}")
        print(f"Try: earthengine authenticate --auth_mode=localhost --force")
        sys.exit(1)


if __name__ == "__main__":
    main()
