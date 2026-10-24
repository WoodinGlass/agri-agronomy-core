"""ParameterDef model (v1.0.0)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agri_core.models.parameter import AppliesTo, ParameterDef

pytestmark = pytest.mark.unit


def _applies(**kw):
    d: dict[str, Any] = {"organism_groups": ["vascular_plant"]}
    d.update(kw)
    return AppliesTo(**d)


def _base(**kw):
    d: dict[str, Any] = dict(
        key="soil_ph",
        stage="site_media",
        shape="trapezoid",
        unit="pH",
        physical_range=(3.0, 10.0),
        phase_set="none",
        applies_to=_applies(),
        scope_keys=["country", "variety"],
        used_by=["thresholds"],
        tier_required=False,
        safety_class="none",
        rationale=None,
        kind="core",
        description="Soil or medium pH.",
        introduced_in="1.0.0",
    )
    d.update(kw)
    return d


# --- AppliesTo ---


def test_applies_to_minimal() -> None:
    a = AppliesTo(organism_groups=["vascular_plant"])
    assert a.organism_groups == ["vascular_plant"]
    assert a.archetypes is None
    assert a.uses is None
    assert a.systems is None
    assert a.traits is None


def test_applies_to_organism_groups_required() -> None:
    with pytest.raises(ValidationError):
        AppliesTo()  # type: ignore[call-arg]


def test_applies_to_organism_groups_non_empty() -> None:
    with pytest.raises(ValidationError):
        AppliesTo(organism_groups=[])


def test_applies_to_optional_dimension_non_empty_if_provided() -> None:
    with pytest.raises(ValidationError, match="if provided, must be non-empty"):
        AppliesTo(organism_groups=["vascular_plant"], archetypes=[])


def test_applies_to_optional_dimension_can_be_omitted() -> None:
    AppliesTo(organism_groups=["vascular_plant"])


def test_applies_to_optional_dimension_can_have_values() -> None:
    a = AppliesTo(organism_groups=["vascular_plant"], archetypes=["annual", "biennial"])
    assert a.archetypes == ["annual", "biennial"]


def test_applies_to_frozen() -> None:
    a = AppliesTo(organism_groups=["vascular_plant"])
    with pytest.raises((ValidationError, TypeError)):
        a.organism_groups = ["fungus"]  # type: ignore[misc]


# --- ParameterDef basics ---


def test_parameter_minimal_valid() -> None:
    p = ParameterDef(**_base())
    assert p.key == "soil_ph"
    assert p.shape == "trapezoid"


def test_parameter_name_property_deprecated() -> None:
    p = ParameterDef(**_base())
    assert p.name == p.key


def test_parameter_key_snake_case() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(key="Soil_ph"))


def test_parameter_key_non_ascii_rejected() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(key="s\u00f3il"))


def test_parameter_frozen() -> None:
    p = ParameterDef(**_base())
    with pytest.raises((ValidationError, TypeError)):
        p.key = "other"  # type: ignore[misc]


def test_parameter_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(extra_field="boom"))


def test_parameter_core_requires_used_by() -> None:
    with pytest.raises(ValidationError, match="core parameter requires used_by"):
        ParameterDef(**_base(used_by=[]))


def test_parameter_extension_allows_empty_used_by() -> None:
    p = ParameterDef(**_base(kind="extension", used_by=[]))
    assert p.used_by == []


# --- Shape rules ---


def test_trapezoid_requires_unit() -> None:
    with pytest.raises(ValidationError, match="requires unit"):
        ParameterDef(**_base(unit=None))


def test_trapezoid_requires_physical_range() -> None:
    with pytest.raises(ValidationError, match="requires physical_range"):
        ParameterDef(**_base(physical_range=None))


def test_trapezoid_physical_range_low_lt_high() -> None:
    with pytest.raises(ValidationError, match="low must be < high"):
        ParameterDef(**_base(physical_range=(10.0, 3.0)))


def test_range_shape_valid() -> None:
    p = ParameterDef(**_base(shape="range", unit="kilogram/hectare"))
    assert p.shape == "range"


def test_scalar_shape_valid() -> None:
    p = ParameterDef(**_base(shape="scalar", unit="degree_Celsius"))
    assert p.shape == "scalar"


def test_enum_requires_enum_values_or_source() -> None:
    with pytest.raises(ValidationError, match="requires enum_values or enum_source"):
        ParameterDef(**_base(shape="enum", unit=None, physical_range=None))


def test_enum_with_values_valid() -> None:
    p = ParameterDef(**_base(shape="enum", unit=None, physical_range=None, enum_values=["a", "b"]))
    assert p.enum_values == ["a", "b"]


def test_enum_with_source_valid() -> None:
    p = ParameterDef(
        **_base(shape="enum", unit=None, physical_range=None, enum_source="phases:biological")
    )
    assert p.enum_source == "phases:biological"


def test_enum_rejects_unit() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ParameterDef(**_base(shape="enum", enum_values=["a"]))


def test_enum_set_valid() -> None:
    p = ParameterDef(
        **_base(shape="enum_set", unit=None, physical_range=None, enum_values=["x", "y"])
    )
    assert p.shape == "enum_set"


def test_enum_set_requires_values() -> None:
    with pytest.raises(ValidationError, match="requires enum_values or enum_source"):
        ParameterDef(**_base(shape="enum_set", unit=None, physical_range=None))


def test_enum_rejects_both_sources() -> None:
    with pytest.raises(ValidationError, match="cannot have both"):
        ParameterDef(
            **_base(
                shape="enum", unit=None, physical_range=None, enum_values=["a"], enum_source="x"
            )
        )


def test_bool_rejects_unit() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ParameterDef(**_base(shape="bool", unit="pH", physical_range=None))


def test_rule_requires_schema() -> None:
    with pytest.raises(ValidationError, match="requires rule_schema"):
        ParameterDef(**_base(shape="rule", unit=None, physical_range=None))


def test_rule_with_schema_valid() -> None:
    p = ParameterDef(
        **_base(shape="rule", unit=None, physical_range=None, rule_schema={"type": "object"})
    )
    assert p.shape == "rule"


def test_unknown_shape_valid() -> None:
    p = ParameterDef(**_base(shape="unknown", unit=None, physical_range=None))
    assert p.shape == "unknown"


# --- Safety class ---


def test_safety_class_default_none() -> None:
    p = ParameterDef(**_base())
    assert p.safety_class == "none"
    assert p.safety_critical is False


@pytest.mark.parametrize("cls", ["dose_cap", "toxicity_limit", "regulatory"])
def test_safety_class_requires_rationale(cls: str) -> None:
    with pytest.raises(ValidationError, match="requires rationale"):
        ParameterDef(**_base(safety_class=cls, rationale=None))


@pytest.mark.parametrize("cls", ["dose_cap", "toxicity_limit", "regulatory"])
def test_safety_class_with_rationale_valid(cls: str) -> None:
    p = ParameterDef(**_base(safety_class=cls, rationale="test reason"))
    assert p.safety_critical is True


def test_safety_class_invalid_value() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(safety_class="critical", rationale="x"))


# --- Unit canonical ---


def test_unit_not_in_canonical_rejected() -> None:
    with pytest.raises(ValidationError, match="not in canonical set"):
        ParameterDef(**_base(unit="furlong"))


def test_unit_none_for_enum_ok() -> None:
    ParameterDef(**_base(shape="enum", unit=None, physical_range=None, enum_values=["a"]))


# --- physical_range ---


def test_physical_range_default_none_for_enum() -> None:
    p = ParameterDef(**_base(shape="enum", unit=None, physical_range=None, enum_values=["a"]))
    assert p.physical_range is None


# --- introduced_in ---


def test_introduced_in_semver() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(**_base(introduced_in="1.0"))
