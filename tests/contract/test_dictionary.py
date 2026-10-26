"""Dictionary model: constructors, lookups, hashing."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agri_core.models.dictionary import Dictionary

pytestmark = pytest.mark.unit


def _param(key: str, **kw: Any) -> dict:
    base = {
        "stage": "cycle",
        "shape": "scalar",
        "unit": "day",
        "physical_range": [1.0, 3650.0],
        "phase_set": "none",
        "scope_keys": [],
        "applies_to": {"organism_groups": ["vascular_plant"]},
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


def _dict_data(version: str = "1.0.0", params: dict | None = None) -> dict:
    if params is None:
        params = {"phase_duration": _param("phase_duration")}
    return {"dictionary_version": version, "parameters": params}


def test_construct_minimal() -> None:
    d = Dictionary._from_data(_dict_data())
    assert d.version == "1.0.0"
    assert "phase_duration" in d.parameters


def test_version_must_be_semver() -> None:
    with pytest.raises(ValueError, match="not valid"):
        Dictionary._from_data(_dict_data(version="1.0"))


def test_version_accepts_dev() -> None:
    d = Dictionary._from_data(_dict_data(version="1.0.0-dev"))
    assert d.version == "1.0.0-dev"


def test_lookup() -> None:
    d = Dictionary._from_data(_dict_data())
    p = d.lookup("phase_duration")
    assert p.key == "phase_duration"


def test_lookup_missing() -> None:
    d = Dictionary._from_data(_dict_data())
    with pytest.raises(KeyError):
        d.lookup("nonexistent")


def test_by_stage() -> None:
    params = {
        "a": _param("a", stage="cycle"),
        "b": _param("b", stage="care"),
    }
    d = Dictionary._from_data(_dict_data(params=params))
    assert {p.key for p in d.by_stage("cycle")} == {"a"}


def test_by_module() -> None:
    params = {
        "a": _param("a", used_by=["stages"]),
        "b": _param("b", used_by=["climate"]),
    }
    d = Dictionary._from_data(_dict_data(params=params))
    assert {p.key for p in d.by_module("stages")} == {"a"}


def test_content_hash_stable() -> None:
    d1 = Dictionary._from_data(_dict_data())
    d2 = Dictionary._from_data(_dict_data())
    assert d1.content_hash() == d2.content_hash()


def test_content_hash_differs_with_content() -> None:
    d1 = Dictionary._from_data(_dict_data())
    params2 = {"phase_duration": _param("phase_duration", description="different description")}
    d2 = Dictionary._from_data(_dict_data(params=params2))
    assert d1.content_hash() != d2.content_hash()


def test_content_hash_ignores_version() -> None:
    d1 = Dictionary._from_data(_dict_data(version="1.0.0"))
    d2 = Dictionary._from_data(_dict_data(version="1.0.0-dev"))
    assert d1.content_hash() == d2.content_hash()


def test_invalid_param_shape_raises() -> None:
    with pytest.raises(ValidationError, match="requires physical_range"):
        Dictionary._from_data(
            _dict_data(params={"x": _param("x", shape="trapezoid", physical_range=None, unit="pH")})
        )


# ---- M5-2b: phases_by_archetype loading -------------------------------


def test_real_dictionary_has_phases_by_archetype() -> None:
    from pathlib import Path as _Path

    from agri_core.models.dictionary import Dictionary

    dict_path = _Path(__file__).resolve().parents[2] / "dictionary" / "parameters.core.yaml"
    d = Dictionary.load(dict_path)
    assert len(d.phases_by_archetype) == 8
    assert "aquatic" in d.phases_by_archetype
    assert "vegetative" in d.phases_by_archetype["aquatic"]


def test_load_without_vocab_yields_empty_phases(tmp_path) -> None:
    import yaml

    from agri_core.models.dictionary import Dictionary

    (tmp_path / "parameters.core.yaml").write_text(
        yaml.safe_dump({"dictionary_version": "1.0.0", "parameters": {}}),
        encoding="utf-8",
    )
    d = Dictionary.load(tmp_path / "parameters.core.yaml")
    assert d.phases_by_archetype == {}
