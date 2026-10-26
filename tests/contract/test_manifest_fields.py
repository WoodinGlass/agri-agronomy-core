"""PackManifest fields new in M5-2b: dictionary_min, synthetic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.pack import PackManifest

pytestmark = pytest.mark.contract


def _base() -> dict[str, object]:
    return {
        "name": "test",
        "version": "1.0.0",
        "schema_version": 1,
        "engine_min": "0.0.0",
        "dictionary_min": "1.0.0",
    }


def test_dictionary_min_required() -> None:
    data = _base()
    del data["dictionary_min"]
    with pytest.raises(ValidationError, match="dictionary_min"):
        PackManifest.model_validate(data)


@pytest.mark.parametrize("bad", ["1.0", "1.0.0.0", "1", "v1.0.0"])
def test_dictionary_min_rejects_non_semver(bad: str) -> None:
    data = _base()
    data["dictionary_min"] = bad
    with pytest.raises(ValidationError, match="dictionary_min"):
        PackManifest.model_validate(data)


@pytest.mark.parametrize("ok", ["1.0.0", "2026.10.0", "0.0.1"])
def test_dictionary_min_accepts_semver(ok: str) -> None:
    data = _base()
    data["dictionary_min"] = ok
    m = PackManifest.model_validate(data)
    assert m.dictionary_min == ok


def test_synthetic_defaults_to_false() -> None:
    m = PackManifest.model_validate(_base())
    assert m.synthetic is False


def test_synthetic_accepts_true() -> None:
    data = _base()
    data["synthetic"] = True
    m = PackManifest.model_validate(data)
    assert m.synthetic is True


def test_full_manifest_validates() -> None:
    m = PackManifest.model_validate(_base())
    assert m.name == "test"
    assert m.version == "1.0.0"
    assert m.schema_version == 1
    assert m.engine_min == "0.0.0"
    assert m.dictionary_min == "1.0.0"
    assert m.content_hash is None
    assert m.synthetic is False
