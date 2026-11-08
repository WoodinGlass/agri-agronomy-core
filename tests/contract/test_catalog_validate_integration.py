"""ADR-012: extension parameter matching an excluded catalog row is rejected."""

from __future__ import annotations

import pytest

from agri_core.catalog import matches_excluded
from agri_core.models.dictionary import Dictionary
from agri_core.models.finding import FindingSeverity
from agri_core.models.parameter import ParameterDef
from agri_core.pack.loader import _default_dictionary

pytestmark = pytest.mark.contract

_CORE_DICT = _default_dictionary()


def _base_param() -> ParameterDef:
    for p in sorted(_CORE_DICT.parameters.values(), key=lambda x: x.key):
        if p.shape == "scalar" and p.unit == "percent":
            return p
    return next(p for p in _CORE_DICT.parameters.values() if p.shape == "scalar")


_BASE = _base_param()


def _ext(key: str, **overrides: object) -> ParameterDef:
    base: dict[str, object] = {
        "key": key,
        "kind": "extension",
        "tier_required": False,
    }
    base.update(overrides)
    return _BASE.model_copy(update=base)


def _dictionary_with(*params: ParameterDef) -> Dictionary:
    merged = dict(_CORE_DICT.parameters)
    for p in params:
        merged[p.key] = p
    return _CORE_DICT.model_copy(update={"parameters": merged})


@pytest.mark.parametrize(
    "param_id",
    [
        "exclude_uv_c_dosing",
        "uv_c_dosing",
        "uv_c_dosing_estimated",
        "pesticide_dose",
        "pesticide_dose_adjusted",
        "herbicide_dose_mg_l",
        "fungicide_dose_interval",
        "insecticide_dose_max",
        "lamp_spectrum_recipe",
        "lamp_spectrum_recipe_rgb",
        "postharvest_chemical",
        "postharvest_chemical_treatment",
        "uv_ab_dosing",
        "uv_ab_dosing_watt",
    ],
)
def test_matches_excluded_prefix_match(param_id: str) -> None:
    assert matches_excluded(param_id, prefix_match=True)


@pytest.mark.parametrize(
    "param_id",
    [
        "gdd_base",
        "vpd",
        "dosing_interval",
        "uv_index_forecast",
        "pesticide_residue",
        "chemistry_notes",
        "is_excluded",
    ],
)
def test_matches_excluded_no_match(param_id: str) -> None:
    assert not matches_excluded(param_id, prefix_match=True)


def test_matches_excluded_no_prefix_requires_exact() -> None:
    assert matches_excluded("exclude_uv_c_dosing")
    assert not matches_excluded("uv_c_dosing", prefix_match=False)
    assert not matches_excluded("uv_c_dosing_estimated", prefix_match=False)


def test_rule_fires_on_excluded_extension() -> None:
    from agri_core.pack.validate import check_catalog_excluded_extension

    dictionary = _dictionary_with(_ext("uv_c_dosing_estimated"))
    findings = check_catalog_excluded_extension(
        None,
        {},
        dictionary,  # type: ignore[arg-type]
    )
    codes = {f.code for f in findings}
    assert "PACK_CATALOG_EXCLUDED_PARAMETER" in codes
    assert all(f.severity == FindingSeverity.ERROR for f in findings)


def test_rule_ignores_core_params() -> None:
    from agri_core.pack.validate import check_catalog_excluded_extension

    findings = check_catalog_excluded_extension(
        None,
        {},
        _CORE_DICT,  # type: ignore[arg-type]
    )
    assert findings == []


def test_rule_ignores_non_matching_extension() -> None:
    from agri_core.pack.validate import check_catalog_excluded_extension

    dictionary = _dictionary_with(_ext("gdd_base_extended"))
    findings = check_catalog_excluded_extension(
        None,
        {},
        dictionary,  # type: ignore[arg-type]
    )
    assert findings == []


def test_rule_is_registered_in_rules_tuple() -> None:
    from agri_core.pack.validate import RULES, check_catalog_excluded_extension

    assert check_catalog_excluded_extension in RULES
