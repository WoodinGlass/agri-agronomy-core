"""Bundle loading, contract_hash, and classify_change."""

from __future__ import annotations

import copy

import pytest

from agri_core.models.dictionary import classify_change, contract_hash

pytestmark = pytest.mark.unit


def _param(**kw):
    """A minimal valid parameter dict, deep-copyable."""
    base = {
        "key": "test_param",
        "stage": "care",
        "shape": "scalar",
        "unit": "day",
        "physical_range": [1.0, 10.0],
        "phase_set": "none",
        "applies_to": {"organism_groups": ["vascular_plant"]},
        "scope_keys": ["country"],
        "used_by": ["stages"],
        "tier_required": False,
        "safety_class": "none",
        "rationale": None,
        "kind": "core",
        "description": "test param",
        "introduced_in": "1.0.0",
    }
    base.update(kw)
    return base


def _bundle(**kw):
    base = {
        "version": "1.0.0",
        "parameters": {"test_param": _param()},
        "vocab": {
            "uses": {
                "schema_version": 1,
                "uses": {"vegetable": {}, "fruit": {}},
            },
            "modules": {
                "schema_version": 1,
                "modules": {"stages": {"description": "x", "reads": ["test_param"]}},
            },
        },
        "units": {
            "schema_version": 1,
            "custom_units": {"pH": {"kind": "custom", "description": "pH"}},
        },
    }
    base.update(kw)
    return base


def _mut(**kw):
    """Deep copy of default bundle with top-level overrides."""
    b = copy.deepcopy(_bundle())
    b.update(kw)
    return b


def _with_param(**param_kw):
    b = _bundle()
    b["parameters"]["test_param"] = _param(**param_kw)
    return b


# --- contract_hash ---


def test_contract_hash_stable() -> None:
    assert contract_hash(_bundle()) == contract_hash(_bundle())


def test_contract_hash_differs_on_param_change() -> None:
    a = _bundle()
    b = _with_param(description="changed")
    assert contract_hash(a) != contract_hash(b)


def test_contract_hash_differs_on_vocab_change() -> None:
    a = _bundle()
    b = _bundle()
    b["vocab"]["uses"]["uses"]["herb"] = {}
    assert contract_hash(a) != contract_hash(b)


def test_contract_hash_differs_on_units_change() -> None:
    a = _bundle()
    b = _bundle()
    b["units"]["custom_units"]["ppm"] = {"kind": "custom", "description": "ppm"}
    assert contract_hash(a) != contract_hash(b)


def test_contract_hash_ignores_version() -> None:
    a = _bundle(version="1.0.0")
    b = _bundle(version="1.0.0-dev")
    assert contract_hash(a) == contract_hash(b)


# --- classify_change: PATCH ---


def test_classify_no_change_patch() -> None:
    assert classify_change(_bundle(), _bundle()) == "PATCH"


def test_classify_description_only_patch() -> None:
    a = _bundle()
    b = _with_param(description="new description")
    assert classify_change(a, b) == "PATCH"


def test_classify_rationale_only_patch() -> None:
    a = _with_param(safety_class="dose_cap", rationale="old reason")
    b = _with_param(safety_class="dose_cap", rationale="new reason")
    assert classify_change(a, b) == "PATCH"


# --- classify_change: MAJOR ---


def test_classify_key_removed_major() -> None:
    a = _bundle()
    b = _bundle()
    b["parameters"] = {}
    assert classify_change(a, b) == "MAJOR"


def test_classify_shape_change_major() -> None:
    assert classify_change(_bundle(), _with_param(shape="trapezoid")) == "MAJOR"


def test_classify_unit_change_major() -> None:
    assert classify_change(_bundle(), _with_param(unit="kilogram/hectare")) == "MAJOR"


def test_classify_phase_set_change_major() -> None:
    assert classify_change(_bundle(), _with_param(phase_set="biological")) == "MAJOR"


def test_classify_enum_values_change_major() -> None:
    a = _with_param(shape="enum", unit=None, physical_range=None, enum_values=["a", "b"])
    b = _with_param(shape="enum", unit=None, physical_range=None, enum_values=["a", "b", "c"])
    assert classify_change(a, b) == "MAJOR"


def test_classify_enum_source_change_major() -> None:
    a = _with_param(
        shape="enum_set", unit=None, physical_range=None, enum_source="phases:biological"
    )
    b = _with_param(shape="enum_set", unit=None, physical_range=None, enum_source="uses")
    assert classify_change(a, b) == "MAJOR"


def test_classify_safety_class_change_major() -> None:
    a = _bundle()
    b = _with_param(safety_class="dose_cap", rationale="new")
    assert classify_change(a, b) == "MAJOR"


def test_classify_tier_required_true_major() -> None:
    a = _bundle()
    b = _with_param(tier_required=True)
    assert classify_change(a, b) == "MAJOR"


def test_classify_applies_to_narrowed_major() -> None:
    a = _with_param(applies_to={"organism_groups": ["vascular_plant", "fungus"]})
    b = _with_param(applies_to={"organism_groups": ["vascular_plant"]})
    assert classify_change(a, b) == "MAJOR"


def test_classify_applies_to_from_unlimited_major() -> None:
    a = _with_param(applies_to={"organism_groups": ["vascular_plant"]})
    b = _with_param(applies_to={"organism_groups": ["vascular_plant"], "systems": ["field"]})
    assert classify_change(a, b) == "MAJOR"


def test_classify_scope_keys_narrowed_major() -> None:
    a = _with_param(scope_keys=["country", "region", "variety"])
    b = _with_param(scope_keys=["country", "region"])
    assert classify_change(a, b) == "MAJOR"


def test_classify_allowed_phases_narrowed_major() -> None:
    a = _with_param(allowed_phases=["initial", "development", "midseason"])
    b = _with_param(allowed_phases=["initial", "development"])
    assert classify_change(a, b) == "MAJOR"


def test_classify_physical_range_narrowed_major() -> None:
    a = _with_param(physical_range=[0.0, 100.0])
    b = _with_param(physical_range=[10.0, 100.0])
    assert classify_change(a, b) == "MAJOR"


def test_classify_physical_range_from_unbounded_major() -> None:
    a = _with_param(physical_range=None, shape="enum", unit=None, enum_values=["a"])
    b = _with_param(physical_range=[0.0, 1.0], shape="enum", unit=None, enum_values=["a"])
    assert classify_change(a, b) == "MAJOR"


def test_classify_vocab_value_removed_major() -> None:
    a = _bundle()
    b = _bundle()
    del b["vocab"]["uses"]["uses"]["fruit"]
    assert classify_change(a, b) == "MAJOR"


def test_classify_custom_unit_changed_major() -> None:
    a = _bundle()
    b = _bundle()
    b["units"]["custom_units"]["pH"]["description"] = "changed"
    assert classify_change(a, b) == "MAJOR"


def test_classify_unclassified_change_major() -> None:
    """A field that is not explicitly handled (and not soft) must trigger MAJOR."""
    a = _bundle()
    b = _with_param(kind="extension")
    assert classify_change(a, b) == "MAJOR"


# --- classify_change: MINOR ---


def test_classify_new_key_minor() -> None:
    a = _bundle()
    b = _bundle()
    b["parameters"]["new_param"] = _param(key="new_param")
    assert classify_change(a, b) == "MINOR"


def test_classify_applies_to_widened_minor() -> None:
    a = _with_param(applies_to={"organism_groups": ["vascular_plant"]})
    b = _with_param(applies_to={"organism_groups": ["vascular_plant", "fungus"]})
    assert classify_change(a, b) == "MINOR"


def test_classify_applies_to_to_unlimited_minor() -> None:
    a = _with_param(applies_to={"organism_groups": ["vascular_plant"], "systems": ["field"]})
    b = _with_param(applies_to={"organism_groups": ["vascular_plant"]})
    assert classify_change(a, b) == "MINOR"


def test_classify_scope_keys_widened_minor() -> None:
    a = _with_param(scope_keys=["country"])
    b = _with_param(scope_keys=["country", "region"])
    assert classify_change(a, b) == "MINOR"


def test_classify_allowed_phases_widened_minor() -> None:
    a = _with_param(allowed_phases=["initial"])
    b = _with_param(allowed_phases=["initial", "development"])
    assert classify_change(a, b) == "MINOR"


def test_classify_physical_range_widened_minor() -> None:
    a = _with_param(physical_range=[1.0, 10.0])
    b = _with_param(physical_range=[0.0, 100.0])
    assert classify_change(a, b) == "MINOR"


def test_classify_vocab_value_added_minor() -> None:
    a = _bundle()
    b = _bundle()
    b["vocab"]["uses"]["uses"]["herb"] = {}
    assert classify_change(a, b) == "MINOR"


def test_classify_custom_unit_added_minor() -> None:
    a = _bundle()
    b = _bundle()
    b["units"]["custom_units"]["ppm"] = {"kind": "custom", "description": "ppm"}
    assert classify_change(a, b) == "MINOR"
