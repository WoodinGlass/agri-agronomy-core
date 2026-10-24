"""Identifier types for agri-knowledge rows.

All identifiers use Crockford base32 (uppercase, excludes I, L, O, U) with
a single uppercase ASCII letter prefix. Case is strict: lowercase input is
rejected to guarantee deterministic identity. Callers that need to accept
non-canonical input should normalize (uppercase) before validating.

Prefixes:
    T  taxon_id    T + 9 chars    total 10
    F  fact_id     F + 11+ chars  total >= 12
    D  dataset_id  D + 9 chars    total 10
    S  source_id   S + 3+ digits  total >= 4 (unchanged from M0r)
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford base32 alphabet: 0-9 and A-Z excluding I, L, O, U (32 chars)."""

CROCKFORD_CHARS = "0-9A-HJKMNP-TV-Z"
"""Regex character class matching one Crockford base32 character."""

_TAXON_ID_PATTERN = rf"^T[{CROCKFORD_CHARS}]{{9}}$"
_FACT_ID_PATTERN = rf"^F[{CROCKFORD_CHARS}]{{11,}}$"
_DATASET_ID_PATTERN = rf"^D[{CROCKFORD_CHARS}]{{9}}$"
_SOURCE_ID_PATTERN = r"^S\d{3,}$"

TaxonId = Annotated[str, Field(pattern=_TAXON_ID_PATTERN)]
"""Taxon identifier: 'T' followed by exactly 9 Crockford base32 characters."""

FactId = Annotated[str, Field(pattern=_FACT_ID_PATTERN)]
"""Fact identifier: 'F' followed by at least 11 Crockford base32 characters."""

DatasetId = Annotated[str, Field(pattern=_DATASET_ID_PATTERN)]
"""Dataset identifier: 'D' followed by exactly 9 Crockford base32 characters."""

SourceId = Annotated[str, Field(pattern=_SOURCE_ID_PATTERN)]
"""Source identifier: 'S' followed by at least 3 decimal digits. Same as M0r."""

__all__ = [
    "CROCKFORD_ALPHABET",
    "CROCKFORD_CHARS",
    "DatasetId",
    "FactId",
    "SourceId",
    "TaxonId",
    "ensure_src_or_dataset",
]


def ensure_src_or_dataset(src: list[str] | None, dataset_id: str | None) -> None:
    """Enforce the W5 rule: at least one of src or dataset_id must be present.

    Raises ``ValueError`` if both are missing or empty. Callers use this from
    a Pydantic ``model_validator(mode="after")``.
    """
    has_src = bool(src)
    has_dataset = bool(dataset_id)
    if not has_src and not has_dataset:
        raise ValueError("at least one of src or dataset_id is required")
