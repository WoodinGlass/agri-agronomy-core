"""Prepare src/agri_core/{_data,_dictionary} for maturin wheel build.

Maturin does not relocate files (unlike hatchling's force-include).
We copy schema/ and dictionary/ into the Python package tree so
`python-source = "src"` picks them up.

Run before `maturin build` or `python -m build`:
    python scripts/wheel_prep.py

Idempotent. Safe to re-run.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    src = repo / "src" / "agri_core"
    if not src.is_dir():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    copies = [
        (repo / "schema", src / "_data" / "schema"),
        (repo / "dictionary", src / "_dictionary"),
    ]
    for source, dest in copies:
        if not source.is_dir():
            print(f"error: {source} not found", file=sys.stderr)
            return 1
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest)
        print(f"copied {source} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
