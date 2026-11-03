"""Result envelope: subject and request_id (ADR-009)."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agri_core.models.canonical import canonical_json


class Subject(BaseModel):
    """What a calculation was about (ADR-009).

    ``taxon_id`` and ``scope`` are ``None``/empty for calculations with
    no taxon (VPD from weather, temperature from elevation).
    ``calculation`` is the stable name of the calculation function.
    ``calculation_version`` is semver; starts at ``"0.1.0"`` for M10.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    taxon_id: str | None = None
    taxon_name: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    calculation: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    calculation_version: str = Field(min_length=1, pattern=r"^\d+\.\d+\.\d+$")


def compute_request_id(
    *,
    subject: Subject | None,
    inputs: dict[str, Any],
    pack_hash: str | None = None,
) -> str:
    """Deterministic ``"req_<32 hex>"`` id (ADR-009). Pure, no I/O."""
    from agri_core import __version__ as engine_version

    payload: dict[str, Any] = {
        "subject": subject.model_dump(mode="json") if subject is not None else None,
        "inputs": inputs,
        "engine_version": engine_version,
        "pack_hash": pack_hash,
    }
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    return "req_" + digest[:32]


__all__ = ["Subject", "compute_request_id"]
