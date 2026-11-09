"""climate_indices.yaml structure + loader validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from agri_core.models.units import CANONICAL_UNITS

pytestmark = pytest.mark.contract

VOCAB = Path(__file__).resolve().parents[2] / "dictionary" / "vocab"
INDICES_FILE = VOCAB / "climate_indices.yaml"

_VALID_OPERATORS = {"lt", "le", "gt", "ge"}
_VALID_AGGREGATIONS = {
    "count", "max_run", "max_rolling_sum", "sum", "min", "max",
}
_EXPECTED_INDICES = {
    "frost_days", "heat_days", "dry_days", "wet_days",
    "frost_spell_max", "heat_spell_max", "dry_spell_max", "wet_spell_max",
    "rolling_sum_7d_max", "rolling_sum_30d_max",
    "precip_total", "temp_min", "temp_max",
}


def _load() -> dict[str, Any]:
    data = yaml.safe_load(INDICES_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "climate_indices.yaml is not a mapping"
    return cast(dict[str, Any], data)


def test_file_exists() -> None:
    assert INDICES_FILE.is_file()


def test_schema_version_is_one() -> None:
    assert _load()["schema_version"] == 1


def test_indices_section_present() -> None:
    data = _load()
    assert "indices" in data
    assert isinstance(data["indices"], dict)


def test_all_expected_indices_present() -> None:
    data = _load()
    assert set(data["indices"]) == _EXPECTED_INDICES, (
        f"missing: {_EXPECTED_INDICES - set(data['indices'])}; "
        f"extra: {set(data['indices']) - _EXPECTED_INDICES}"
    )


def test_each_index_has_required_fields() -> None:
    for name, spec in _load()["indices"].items():
        assert isinstance(spec, dict), f"{name}: not a dict"
        for field in ("description", "unit", "operator", "aggregation"):
            assert field in spec, f"{name}: missing {field!r}"
        assert isinstance(spec["description"], str), f"{name}: description not str"
        assert spec["description"], f"{name}: description empty"


def test_each_index_unit_is_canonical() -> None:
    for name, spec in _load()["indices"].items():
        assert spec["unit"] in CANONICAL_UNITS, (
            f"{name}: unit {spec['unit']!r} not in CANONICAL_UNITS"
        )


def test_each_index_operator_valid() -> None:
    for name, spec in _load()["indices"].items():
        assert spec["operator"] in _VALID_OPERATORS, (
            f"{name}: operator {spec['operator']!r} invalid"
        )


def test_each_index_aggregation_valid() -> None:
    for name, spec in _load()["indices"].items():
        assert spec["aggregation"] in _VALID_AGGREGATIONS, (
            f"{name}: aggregation {spec['aggregation']!r} invalid"
        )


def test_threshold_null_only_for_min_max() -> None:
    for name, spec in _load()["indices"].items():
        agg = spec["aggregation"]
        thr = spec.get("threshold")
        if agg in ("min", "max"):
            assert thr is None, (
                f"{name}: aggregation {agg!r} but threshold={thr!r} "
                f"(should be null)"
            )
        else:
            assert thr is not None, (
                f"{name}: aggregation {agg!r} requires numeric threshold"
            )


def test_window_days_only_for_max_rolling_sum() -> None:
    for name, spec in _load()["indices"].items():
        agg = spec["aggregation"]
        wd = spec.get("window_days")
        if agg == "max_rolling_sum":
            assert isinstance(wd, int), f"{name}: window_days must be int"
            assert wd >= 1, f"{name}: window_days must be >= 1"
        else:
            assert wd is None, (
                f"{name}: aggregation {agg!r} but window_days={wd!r} "
                f"(should be null)"
            )


def test_bundle_loads_indices() -> None:
    from agri_core.models.dictionary import load_bundle_from_root

    root = Path(__file__).resolve().parents[2] / "dictionary"
    bundle = load_bundle_from_root(root)
    assert "climate_indices" in bundle["vocab"]
    assert bundle["vocab"]["climate_indices"]["indices"] == _load()["indices"]
