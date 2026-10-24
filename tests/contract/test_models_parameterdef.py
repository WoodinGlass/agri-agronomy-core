"""ParameterDef model tests."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agri_core.models.parameter import AppliesTo, ParameterDef

pytestmark = pytest.mark.unit


def _base(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = dict(
        name="soil_ph",
        stage="site_media",
        shape="trapezoid",
        unit="pH",
        physical_range=(3.0, 10.0),
        phase_set="none",
        applies_to=AppliesTo(
            archetypes=["annual"], uses=["vegetable"], systems=["field"], traits=[]
        ),
        kind="core",
        used_by=["thresholds"],
        tier_required=False,
        safety_critical=False,
        description="Soil or medium pH.",
        introduced_in="0.1.0",
    )
    d.update(kw)
    return d


def test_minimal_valid() -> None:
    p = ParameterDef(**_base())
    assert p.shape == "trapezoid"
    assert p.kind == "core"
    assert p.used_by == ["thresholds"]


def test_enum_requires_enum_values() -> None:
    with pytest.raises(ValidationError, match="shape=enum requires"):
        ParameterDef(
            **_base(
                name="photoperiod_type",
                shape="enum",
                unit=None,
                enum_values=None,
                physical_range=None,
            )
        )


def test_enum_rejects_unit() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ParameterDef(
            **_base(
                name="p",
                shape="enum",
                enum_values=["a", "b"],
                unit="pH",
                physical_range=None,
            )
        )


def test_bool_rejects_unit() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ParameterDef(**_base(name="b", shape="bool", unit="pH", physical_range=None))


def test_unknown_rejects_unit() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ParameterDef(**_base(name="u", shape="unknown", unit="pH", physical_range=None))


def test_rule_requires_rule_schema() -> None:
    with pytest.raises(ValidationError, match="shape=rule requires"):
        ParameterDef(
            **_base(
                name="r",
                shape="rule",
                unit=None,
                rule_schema=None,
                physical_range=None,
            )
        )


def test_core_requires_used_by() -> None:
    with pytest.raises(ValidationError, match="must declare at least one used_by"):
        ParameterDef(**_base(used_by=[]))


def test_extension_allows_empty_used_by() -> None:
    p = ParameterDef(**_base(kind="extension", used_by=[]))
    assert p.used_by == []
    assert p.kind == "extension"


def test_enum_values_only_for_enum() -> None:
    with pytest.raises(ValidationError, match="enum_values only allowed"):
        ParameterDef(**_base(name="bad", enum_values=["a"]))


def test_rule_schema_only_for_rule() -> None:
    with pytest.raises(ValidationError, match="rule_schema only allowed"):
        ParameterDef(**_base(name="bad", rule_schema={"type": "object"}))


def test_physical_range_low_must_be_less_than_high() -> None:
    with pytest.raises(ValidationError, match="physical_range low"):
        ParameterDef(**_base(physical_range=(10.0, 3.0)))


def test_name_must_be_snake_case() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(name="Soil_ph"))


def test_name_rejects_non_ascii() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(name="ph_tanah_\u00e9"))


def test_introduced_in_must_be_semver() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(introduced_in="1.0"))


def test_deprecated_in_must_be_semver_if_present() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(deprecated_in="1.0"))


def test_frozen() -> None:
    p = ParameterDef(**_base())
    with pytest.raises((ValidationError, TypeError)):
        p.name = "other"  # type: ignore[misc]


def test_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(extra_field="boom"))


def test_applies_to_defaults_to_empty_lists() -> None:
    a = AppliesTo()
    assert a.archetypes == []
    assert a.uses == []
    assert a.systems == []
    assert a.traits == []
    assert a.organism_groups is None
