"""Pack manifest model."""

from __future__ import annotations

import re

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SEMVER3_RE = re.compile(r"^\d+\.\d+\.\d+$")
_HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def _check_semver3(value: str, field: str) -> str:
    if not _SEMVER3_RE.match(value):
        raise ValueError(f"{field} must be X.Y.Z with 3 release components, got {value!r}")
    try:
        Version(value)
    except InvalidVersion as exc:
        raise ValueError(f"{field} is not a valid version: {value!r}") from exc
    return value


class PackManifest(BaseModel):
    """Parsed ``pack.toml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    schema_version: int = Field(strict=True, ge=1)
    engine_min: str
    dictionary_min: str
    content_hash: str | None = None
    synthetic: bool = False

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name must match ^[a-z][a-z0-9_-]{0,63}$")
        return v

    @field_validator("version")
    @classmethod
    def _version_ok(cls, v: str) -> str:
        return _check_semver3(v, "version")

    @field_validator("engine_min")
    @classmethod
    def _engine_ok(cls, v: str) -> str:
        return _check_semver3(v, "engine_min")

    @field_validator("dictionary_min")
    @classmethod
    def _dictionary_min_ok(cls, v: str) -> str:
        return _check_semver3(v, "dictionary_min")

    @field_validator("content_hash")
    @classmethod
    def _content_hash_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _HASH_RE.match(v):
            raise ValueError("content_hash must be 'sha256:<64 lowercase hex>'")
        return v
