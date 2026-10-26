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


# ---- build fields (M6-1): all-or-none, patterns, types ----------------


def test_build_fields_all_or_none_zero() -> None:
    # source manifest: no build fields -> valid
    m = PackManifest.model_validate(_base())
    assert m.artifact_sha256 is None
    assert m.sqlite_schema_version is None
    assert m.built_by is None


def test_build_fields_all_or_none_all() -> None:
    data = _base()
    data["content_hash"] = "sha256:" + "a" * 64
    data["artifact_sha256"] = "sha256:" + "b" * 64
    data["sqlite_schema_version"] = 1
    data["built_by"] = "agri-core 0.0.0"
    m = PackManifest.model_validate(data)
    assert m.artifact_sha256 is not None
    assert m.sqlite_schema_version == 1
    assert m.built_by is not None


@pytest.mark.parametrize(
    "partial_fields",
    [
        {"artifact_sha256": "sha256:" + "a" * 64},
        {"sqlite_schema_version": 1},
        {"built_by": "agri-core 0.0.0"},
        {"artifact_sha256": "sha256:" + "a" * 64, "sqlite_schema_version": 1},
        {"artifact_sha256": "sha256:" + "a" * 64, "built_by": "agri-core 0.0.0"},
        {"sqlite_schema_version": 1, "built_by": "agri-core 0.0.0"},
    ],
)
def test_build_fields_partial_raises(partial_fields: dict[str, object]) -> None:
    data = _base()
    data.update(partial_fields)
    with pytest.raises(ValidationError, match=r"all set .* or all None"):
        PackManifest.model_validate(data)


def test_artifact_sha256_pattern_enforced() -> None:
    data = _base()
    data["artifact_sha256"] = "sha256:not-hex"
    data["sqlite_schema_version"] = 1
    data["built_by"] = "agri-core 0.0.0"
    with pytest.raises(ValidationError, match="artifact_sha256"):
        PackManifest.model_validate(data)


def test_sqlite_schema_version_strict_and_ge_1() -> None:
    data = _base()
    data["artifact_sha256"] = "sha256:" + "a" * 64
    data["sqlite_schema_version"] = 0
    data["built_by"] = "agri-core 0.0.0"
    with pytest.raises(ValidationError, match="sqlite_schema_version"):
        PackManifest.model_validate(data)


def test_built_by_min_length_1() -> None:
    data = _base()
    data["artifact_sha256"] = "sha256:" + "a" * 64
    data["sqlite_schema_version"] = 1
    data["built_by"] = ""
    with pytest.raises(ValidationError, match="built_by"):
        PackManifest.model_validate(data)
