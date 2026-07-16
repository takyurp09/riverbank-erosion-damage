#!/usr/bin/env python3
"""Download ISIMIP3b CWatM discharge for Bangladesh bbox via files.isimip.org API (no login)."""

from __future__ import annotations

import argparse
import io
import re
import time
import zipfile
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
API = "https://data.isimip.org/api/v1"
FILES_API = "https://files.isimip.org/api/v2"

GCMS = [
    "gfdl-esm4",
    "ipsl-cm6a-lr",
    "mpi-esm1-2-hr",
    "mri-esm2-0",
    "ukesm1-0-ll",
]
SCENARIOS = ["historical", "ssp126", "ssp585"]

# Files needed for baseline (1990–2014) + projections (2015–2050)
HISTORICAL_SUFFIXES = ("1991_2000", "2001_2010", "2011_2014")
FUTURE_SUFFIXES = ("2015_2020", "2021_2030", "2031_2040", "2041_2050")


def load_bbox() -> list[float]:
    with open(ROOT / "config" / "settings.yaml") as f:
        cfg = yaml.safe_load(f)
    bb = cfg["bbox"]
    return [bb["west"], bb["east"], bb["south"], bb["north"]]


def list_files(gcm: str, scenario: str) -> list[dict]:
    query = f"cwatm {gcm} {scenario} dis global daily"
    results: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{API}/files/",
            params={"query": query, "page_size": 50, "page": page},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("next"):
            break
        page += 1
    return results


def year_suffix(path: str) -> str | None:
    m = re.search(r"_(\d{4}_\d{4})\.nc$", path)
    return m.group(1) if m else None


def should_download(scenario: str, suffix: str) -> bool:
    if scenario == "historical":
        return suffix in HISTORICAL_SUFFIXES
    return suffix in FUTURE_SUFFIXES


def out_name(gcm: str, scenario: str, suffix: str) -> str:
    return f"dis_{gcm}_{scenario}_{suffix}.nc"


def submit_bbox_job(path: str, bbox: list[float]) -> str:
    payload = {
        "paths": [path],
        "operations": [
            {
                "operation": "select_bbox",
                "bbox": bbox,
                "compute_mean": False,
                "output_csv": False,
            }
        ],
    }
    r = requests.post(FILES_API, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


def wait_for_job(job_id: str, poll_sec: float = 2.0, timeout_sec: float = 600.0) -> str:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = requests.get(f"{FILES_API}/{job_id}", timeout=60)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status == "finished" and data.get("file_url"):
            return data["file_url"]
        if status in {"failed", "error"}:
            raise RuntimeError(f"ISIMIP job {job_id} failed: {data}")
        time.sleep(poll_sec)
    raise TimeoutError(f"ISIMIP job {job_id} timed out")


def download_zip_nc(file_url: str, dest: Path, retries: int = 3) -> None:
    for attempt in range(retries):
        r = requests.get(file_url, timeout=300)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            nc_names = [n for n in zf.namelist() if n.endswith(".nc")]
            if not nc_names:
                if attempt + 1 < retries:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise RuntimeError(f"No NetCDF in zip from {file_url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(nc_names[0]) as src, open(dest, "wb") as dst:
                dst.write(src.read())
        return


def download_all(out_dir: Path, gcms: list[str], scenarios: list[str], dry_run: bool = False) -> None:
    bbox = load_bbox()
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = 0

    for gcm in gcms:
        for scenario in scenarios:
            files = list_files(gcm, scenario)
            for f in files:
                suffix = year_suffix(f["path"])
                if not suffix or not should_download(scenario, suffix):
                    continue
                dest = out_dir / out_name(gcm, scenario, suffix)
                if dest.exists() and dest.stat().st_size > 0:
                    print(f"skip existing {dest.name}")
                    continue
                jobs += 1
                print(f"queue {dest.name} ({f['path'].split('/')[-1]})")
                if dry_run:
                    continue
                for attempt in range(3):
                    try:
                        job_id = submit_bbox_job(f["path"], bbox)
                        file_url = wait_for_job(job_id)
                        download_zip_nc(file_url, dest, retries=1)
                        break
                    except Exception as exc:
                        if attempt + 1 >= 3:
                            raise
                        print(f"retry {dest.name} ({exc})")
                        time.sleep(10 * (attempt + 1))
                print(f"saved {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")

    print(f"\nDone — {jobs} file(s) queued/processed → {out_dir}")
    if not dry_run:
        print("Next: python scripts/data_prep/process_isimip_discharge.py")


def main() -> None:
    p = argparse.ArgumentParser(description="Download ISIMIP3b discharge (Bangladesh bbox cutout)")
    p.add_argument("--gcm", action="append", help="Limit to one GCM (repeatable)")
    p.add_argument("--scenario", action="append", choices=SCENARIOS, help="Limit scenarios")
    p.add_argument("--dry-run", action="store_true", help="List files only")
    args = p.parse_args()

    gcms = args.gcm or GCMS
    scenarios = args.scenario or SCENARIOS
    out_dir = ROOT / "data/processed/climate/isimip"
    download_all(out_dir, gcms, scenarios, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
