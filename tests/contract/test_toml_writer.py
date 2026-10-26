"""Deterministic TOML serializer for built manifests."""

from __future__ import annotations

import tomllib

import pytest

from agri_core.pack.manifest import PackManifest
from agri_core.pack.toml_writer import dump_manifest

pytestmark = pytest.mark.contract


def _source_manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )


def _built_manifest() -> PackManifest:
    return PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
            "content_hash": "sha256:" + "a" * 64,
            "artifact_sha256": "sha256:" + "b" * 64,
            "sqlite_schema_version": 1,
            "built_by": "agri-core 0.0.0",
        }
    )


def test_roundtrip_via_tomllib() -> None:
    m = _built_manifest()
    parsed = tomllib.loads(dump_manifest(m).decode("utf-8"))
    assert parsed["name"] == m.name
    assert parsed["version"] == m.version
    assert parsed["schema_version"] == m.schema_version
    assert parsed["engine_min"] == m.engine_min
    assert parsed["dictionary_min"] == m.dictionary_min
    assert parsed["content_hash"] == m.content_hash
    assert parsed["artifact_sha256"] == m.artifact_sha256
    assert parsed["sqlite_schema_version"] == m.sqlite_schema_version
    assert parsed["built_by"] == m.built_by


def test_roundtrip_via_pydantic() -> None:
    m = _built_manifest()
    parsed = tomllib.loads(dump_manifest(m).decode("utf-8"))
    restored = PackManifest.model_validate(parsed)
    assert restored == m


def test_none_fields_omitted() -> None:
    m = _source_manifest()
    out = dump_manifest(m).decode("utf-8")
    assert "content_hash" not in out
    assert "artifact_sha256" not in out
    assert "sqlite_schema_version" not in out
    assert "built_by" not in out


def test_key_order_stable() -> None:
    m = _built_manifest()
    b1 = dump_manifest(m)
    b2 = dump_manifest(m)
    assert b1 == b2


def test_boolean_before_int() -> None:
    # synthetic=True must render "true" (bool), not "1" (int)
    m = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
            "synthetic": True,
        }
    )
    out = dump_manifest(m).decode("utf-8")
    assert "synthetic = true" in out
    # schema_version is int
    assert "schema_version = 1\n" in out


def test_escape_quotes_backslash() -> None:
    m = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
            "artifact_sha256": "sha256:" + "a" * 64,
            "sqlite_schema_version": 1,
            "built_by": 'agri-core "quoted" \\ backslash',
        }
    )
    out = dump_manifest(m).decode("utf-8")
    parsed = tomllib.loads(out)
    assert parsed["built_by"] == m.built_by


def test_escape_newline_and_control() -> None:
    # built_by can't contain newline (min_length only), but artifact of
    # escaping is checked by constructing a manifest with a name that does
    # not contain newline; the escape helper is tested indirectly via a
    # synthetic string. Use a manifest whose string field carries control
    # chars is not possible with the current model, so test escape via
    # _toml_str indirectly: a valid built_by containing tab would fail
    # min_length if empty; here we use a real tab that Pydantic accepts.
    m = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
            "artifact_sha256": "sha256:" + "a" * 64,
            "sqlite_schema_version": 1,
            "built_by": "x\ty",  # contains a real tab
        }
    )
    out = dump_manifest(m).decode("utf-8")
    parsed = tomllib.loads(out)
    assert parsed["built_by"] == m.built_by
    assert "\\t" in out  # tab escaped in serialized form


def test_trailing_newline() -> None:
    m = _source_manifest()
    out = dump_manifest(m)
    assert out.endswith(b"\n")
    assert not out.endswith(b"\n\n")


def test_fully_populated_roundtrip() -> None:
    m = PackManifest.model_validate(
        {
            "name": "test",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
            "synthetic": True,
            "content_hash": "sha256:" + "1" * 64,
            "artifact_sha256": "sha256:" + "2" * 64,
            "sqlite_schema_version": 1,
            "built_by": "agri-core 9.9.9",
        }
    )
    out = dump_manifest(m).decode("utf-8")
    parsed = tomllib.loads(out)
    restored = PackManifest.model_validate(parsed)
    assert restored == m
