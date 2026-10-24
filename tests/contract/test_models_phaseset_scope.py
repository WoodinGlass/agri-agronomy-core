"""PhaseSet and ScopeKey model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models.phase_set import PhaseSet
from agri_core.models.scope_key import ScopeKey

pytestmark = pytest.mark.unit


# --- PhaseSet ---


def test_phaseset_minimal() -> None:
    ps = PhaseSet(
        name="kc",
        source="kc",
        phases=["initial", "development", "midseason", "late_season"],
    )
    assert ps.source == "kc"
    assert len(ps.phases) == 4


def test_phaseset_none_has_empty_phases() -> None:
    ps = PhaseSet(name="none", source="none")
    assert ps.phases == []


def test_phaseset_name_must_be_snake_case() -> None:
    with pytest.raises(ValidationError):
        PhaseSet(name="KC", source="kc")


def test_phaseset_source_must_be_known() -> None:
    with pytest.raises(ValidationError):
        PhaseSet(name="bad", source="bogus")  # type: ignore[arg-type]


def test_phaseset_frozen() -> None:
    ps = PhaseSet(name="kc", source="kc")
    with pytest.raises((ValidationError, TypeError)):
        ps.name = "other"  # type: ignore[misc]


def test_phaseset_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        PhaseSet(name="kc", source="kc", extra="boom")


def test_phaseset_custom_source() -> None:
    ps = PhaseSet(name="my_custom", source="custom", phases=["a", "b"])
    assert ps.source == "custom"


# --- ScopeKey ---


def test_scopekey_string_with_vocab() -> None:
    sk = ScopeKey(key="country", type="string", vocab="iso_3166_1_alpha2", multi=True)
    assert sk.type == "string"
    assert sk.vocab == "iso_3166_1_alpha2"


def test_scopekey_string_without_vocab() -> None:
    sk = ScopeKey(key="variety", type="string", multi=True)
    assert sk.vocab is None
    assert sk.values is None


def test_scopekey_enum_with_vocab() -> None:
    sk = ScopeKey(key="system", type="enum", vocab="systems", multi=True)
    assert sk.vocab == "systems"


def test_scopekey_enum_with_values() -> None:
    sk = ScopeKey(key="growth_habit", type="enum", values=["rosette", "vine"])
    assert sk.values == ["rosette", "vine"]


def test_scopekey_enum_requires_vocab_or_values() -> None:
    with pytest.raises(ValidationError, match="requires vocab or values"):
        ScopeKey(key="bad", type="enum")


def test_scopekey_enum_rejects_both() -> None:
    with pytest.raises(ValidationError, match="cannot have both vocab and values"):
        ScopeKey(key="bad", type="enum", vocab="systems", values=["a"])


def test_scopekey_range_requires_unit() -> None:
    with pytest.raises(ValidationError, match="type=range requires unit"):
        ScopeKey(key="bad", type="range")


def test_scopekey_range_with_unit() -> None:
    sk = ScopeKey(key="elevation_m", type="range", unit="m", multi=False)
    assert sk.unit == "m"
    assert sk.multi is False


def test_scopekey_non_range_must_have_unit_null() -> None:
    with pytest.raises(ValidationError, match="must have unit=null"):
        ScopeKey(key="bad", type="string", unit="m")


def test_scopekey_key_must_be_snake_case() -> None:
    with pytest.raises(ValidationError):
        ScopeKey(key="Country", type="string")


def test_scopekey_frozen() -> None:
    sk = ScopeKey(key="country", type="string", vocab="iso_3166_1_alpha2")
    with pytest.raises((ValidationError, TypeError)):
        sk.key = "other"  # type: ignore[misc]


def test_scopekey_multi_default_true() -> None:
    sk = ScopeKey(key="country", type="string")
    assert sk.multi is True


def test_scopekey_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ScopeKey(key="country", type="string", extra="boom")
