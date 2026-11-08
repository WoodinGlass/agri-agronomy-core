"""Generator drift: docs and shipped excluded list are in sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_climate_catalog_doc.py"


def test_generator_check_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_generator_check_idempotent() -> None:
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert r.returncode == 0, r.stdout + r.stderr


def test_excluded_generated_has_fmt_off_marker() -> None:
    p = ROOT / "src" / "agri_core" / "catalog" / "_excluded_generated.py"
    text = p.read_text(encoding="utf-8")
    assert "# fmt: off" in text
