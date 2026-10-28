"""from_rows / _build pack_hash + dictionary_version validation (M8-1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.models.dictionary import Dictionary
from agri_core.pack import InMemoryKnowledgeSet, PackManifest

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")


def _manifest(content_hash: str | None = None) -> PackManifest:
    data = {
        "name": "t",
        "version": "1.0.0",
        "schema_version": 1,
        "engine_min": "0.0.0",
        "dictionary_min": "1.0.0",
    }
    if content_hash is not None:
        data["content_hash"] = content_hash
    return PackManifest.model_validate(data)


def test_from_rows_rejects_bad_pack_hash_format() -> None:
    with pytest.raises(ValueError, match=r"pack_hash must match"):
        InMemoryKnowledgeSet.from_rows(
            manifest=_manifest(),
            pack_hash="not-valid",
            dictionary_version=_DICT.version,
            dictionary=_DICT,
        )


def test_from_rows_rejects_pack_hash_mismatch_with_manifest() -> None:
    manifest = _manifest(content_hash="sha256:" + "a" * 64)
    other = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match=r"pack_hash .* != manifest\.content_hash"):
        InMemoryKnowledgeSet.from_rows(
            manifest=manifest,
            pack_hash=other,
            dictionary_version=_DICT.version,
            dictionary=_DICT,
        )


def test_from_rows_rejects_dictionary_version_mismatch() -> None:
    with pytest.raises(ValueError, match=r"dictionary_version .* != dictionary\.version"):
        InMemoryKnowledgeSet.from_rows(
            manifest=_manifest(),
            pack_hash="sha256:" + "1" * 64,
            dictionary_version="9.9.9",
            dictionary=_DICT,
        )
