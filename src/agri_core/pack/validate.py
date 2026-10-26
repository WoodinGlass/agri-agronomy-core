"""Validate a source pack from in-memory allowlist bytes (M6-4)."""

from __future__ import annotations

from collections.abc import Mapping

from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.pack.loader import load_knowledge_set_from_files

__all__ = ["validate_pack"]


def validate_pack(
    files: Mapping[str, bytes],
    *,
    allow_synthetic: bool = False,
    expected_hash: str | None = None,
    dictionary: Dictionary | None = None,
) -> KnowledgeSet:
    """Validate a source pack from already-read allowlist bytes.

    Single entry point for structural validation. Callers that already
    have ``files`` in memory should use this instead of calling
    ``load_knowledge_set_from_files`` directly, so future validation
    logic (M7 report type, additional checks) lands in one place.

    Raises any ``PackError`` subclass that structural validation would
    raise: ``PACK_INVALID``, ``PACK_HASH_MISMATCH``,
    ``PACK_SYNTHETIC_NOT_ALLOWED``, ``PACK_FK_VIOLATION``,
    ``PACK_UNKNOWN_PARAMETER``, and so on.
    """
    return load_knowledge_set_from_files(
        files,
        allow_synthetic=allow_synthetic,
        expected_hash=expected_hash,
        dictionary=dictionary,
    )
