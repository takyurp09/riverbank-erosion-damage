#!/usr/bin/env python3
"""Re-run ISIMIP→GloFAS validation from harmonized discharge (wrapper)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    harmonize = ROOT / "scripts/data_prep/harmonize_isimip_discharge.py"
    subprocess.run([sys.executable, str(harmonize)], check=True)
    print("Validation refreshed via harmonize_isimip_discharge.py")


if __name__ == "__main__":
    main()
