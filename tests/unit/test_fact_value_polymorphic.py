"""FactValue polymorphic shapes: valid + invalid for each of the seven."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models.fact import FactRow

pytestmark = pytest.mark.unit


def _base(**kw):
    d = dict(
        fact_id="F01234567890",
        taxon_id="T012345678",
        parameter="soil_ph",
        phase=None,
        value={"shape": "unknown", "reason": "test"},
        scope={},
        provenance_kind="curated",
        src=["S001"],
        dataset_id=None,
        locator="page 1",
        evidence="A",
        status="draft",
        reviewed_by=None,
        reviewed_at=None,
        superseded_by=None,
    )
    d.update(kw)
    return d


# --- trapezoid ---


def test_trapezoid_valid() -> None:
    FactRow(**_base(value={"shape": "trapezoid", "unit": "pH", "pts": [3.0, 6.0, 7.0, 10.0]}))


def test_trapezoid_equal_bounds_valid() -> None:
    FactRow(**_base(value={"shape": "trapezoid", "unit": "pH", "pts": [7.0, 7.0, 7.0, 7.0]}))


def test_trapezoid_pts_not_ordered_rejected() -> None:
    with pytest.raises(ValidationError, match="pts must satisfy"):
        FactRow(**_base(value={"shape": "trapezoid", "unit": "pH", "pts": [10.0, 6.0, 7.0, 3.0]}))


def test_trapezoid_wrong_pts_count_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "trapezoid", "unit": "pH", "pts": [3.0, 6.0, 10.0]}))


def test_trapezoid_missing_unit_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "trapezoid", "pts": [3.0, 6.0, 7.0, 10.0]}))


# --- range ---


def test_range_valid() -> None:
    FactRow(**_base(value={"shape": "range", "unit": "m", "min": 0.1, "max": 1.5}))


def test_range_min_gt_max_rejected() -> None:
    with pytest.raises(ValidationError, match="must be <= max"):
        FactRow(**_base(value={"shape": "range", "unit": "m", "min": 2.0, "max": 1.0}))


def test_range_missing_unit_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "range", "min": 0.1, "max": 1.5}))


# --- scalar ---


def test_scalar_valid() -> None:
    FactRow(**_base(value={"shape": "scalar", "unit": "dimensionless", "value": 1.1}))


def test_scalar_missing_unit_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "scalar", "value": 1.1}))


# --- enum ---


def test_enum_valid() -> None:
    FactRow(**_base(value={"shape": "enum", "value": "day_neutral"}))


def test_enum_empty_value_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "enum", "value": ""}))


# --- bool ---


def test_bool_true() -> None:
    FactRow(**_base(value={"shape": "bool", "value": True}))


def test_bool_false() -> None:
    FactRow(**_base(value={"shape": "bool", "value": False}))


# --- rule ---


def test_rule_valid() -> None:
    FactRow(**_base(value={"shape": "rule", "data": {"if": "x > 10", "then": "apply"}}))


def test_rule_empty_data_ok() -> None:
    FactRow(**_base(value={"shape": "rule", "data": {}}))


# --- unknown ---


def test_unknown_valid() -> None:
    FactRow(**_base(value={"shape": "unknown", "reason": "no source"}))


def test_unknown_empty_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "unknown", "reason": ""}))


def test_unknown_missing_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "unknown"}))


# --- invalid shape name ---


def test_invalid_shape_name_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"shape": "matrix", "value": 1.0}))


def test_missing_shape_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(value={"unit": "pH", "value": 1.0}))
