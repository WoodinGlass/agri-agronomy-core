"""Drift between Finding models and schema/*.schema.json (M3 pattern)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from agri_core.models.finding import Finding
from agri_core.pack.validate import ValidationReport

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]


def test_finding_schema_matches_model() -> None:
    expected = TypeAdapter(Finding).json_schema(mode="serialization")
    current = json.loads((ROOT / "schema/finding.schema.json").read_text())
    assert current == expected


def test_validation_report_schema_matches_model() -> None:
    expected = TypeAdapter(ValidationReport).json_schema(mode="serialization")
    current = json.loads((ROOT / "schema/validation_report.schema.json").read_text())
    assert current == expected


def test_regen_is_idempotent() -> None:
    before_finding = (ROOT / "schema/finding.schema.json").read_text()
    before_report = (ROOT / "schema/validation_report.schema.json").read_text()
    subprocess.run(
        [sys.executable, "scripts/gen_schemas.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    after_finding = (ROOT / "schema/finding.schema.json").read_text()
    after_report = (ROOT / "schema/validation_report.schema.json").read_text()
    assert before_finding == after_finding
    assert before_report == after_report
