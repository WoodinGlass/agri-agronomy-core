"""Registry drift: YAML ↔ loader ↔ expected set."""

from __future__ import annotations

import pytest

from agri_core.climate import threshold_index
from agri_core.climate.indices import _load_registry

pytestmark = pytest.mark.contract

_EXPECTED = {
    "frost_days",
    "heat_days",
    "dry_days",
    "wet_days",
    "frost_spell_max",
    "heat_spell_max",
    "dry_spell_max",
    "wet_spell_max",
    "rolling_sum_7d_max",
    "rolling_sum_30d_max",
    "precip_total",
    "temp_min",
    "temp_max",
}


def test_registry_loads_13() -> None:
    registry = _load_registry()
    assert len(registry) == 13
    assert set(registry) == _EXPECTED


def test_every_index_has_required_fields() -> None:
    for name, spec in _load_registry().items():
        for field in ("unit", "operator", "aggregation", "description"):
            assert field in spec, f"{name}: missing {field}"
        assert "threshold" in spec, f"{name}: missing 'threshold'"


def test_threshold_index_publicly_exported() -> None:
    assert callable(threshold_index)
