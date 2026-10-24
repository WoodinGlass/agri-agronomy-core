"""In-memory dictionary of parameters (v1.0.0)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from agri_core.models.canonical import canonical_json
from agri_core.models.parameter import ParameterDef, check_semver


class Dictionary(BaseModel):
    """Immutable collection of parameters plus a SemVer version.

    Loading is explicit: pass a path to ``load(path)``, or call
    ``load_packaged()`` to read the copy bundled inside the installed wheel.
    No current-directory lookup and no environment variable. Lookups are
    read-only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    parameters: dict[str, ParameterDef]

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        return check_semver(v)

    @classmethod
    def load(cls, path: Path) -> Dictionary:
        """Load from an explicit path."""
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        return cls._from_data(data)

    @classmethod
    def load_packaged(cls) -> Dictionary:
        """Load the dictionary bundled inside the installed package."""
        from importlib.resources import files as _files

        pkg = _files("agri_core") / "_dictionary" / "parameters.core.yaml"
        text = pkg.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        return cls._from_data(data)

    @classmethod
    def _from_data(cls, data: dict[str, Any]) -> Dictionary:
        params: dict[str, ParameterDef] = {}
        raw_params = data.get("parameters") or {}
        for key, raw in raw_params.items():
            if not re.match(r"^[a-z][a-z0-9_]*$", key):
                raise ValueError(f"parameter key {key!r} not snake_case")
            if key in params:
                raise ValueError(f"parameter key {key!r} duplicated")
            merged = {"key": key, **raw}
            params[key] = ParameterDef.model_validate(merged)
        return cls(version=data["dictionary_version"], parameters=params)

    def lookup(self, key: str) -> ParameterDef:
        if key not in self.parameters:
            raise KeyError(f"parameter {key!r} not in dictionary")
        return self.parameters[key]

    def by_stage(self, stage: str) -> list[ParameterDef]:
        return [p for p in self.parameters.values() if p.stage == stage]

    def by_module(self, module: str) -> list[ParameterDef]:
        return [p for p in self.parameters.values() if module in p.used_by]

    def content_hash(self) -> str:
        """SHA-256 of canonical JSON of the ``parameters`` block.

        Does not include ``dictionary_version``; version change without
        content change yields the same hash. This mirrors the pin file's
        pairing (version + hash), enforced by tests.
        """
        payload = {
            key: self.parameters[key].model_dump(mode="json") for key in sorted(self.parameters)
        }
        return hashlib.sha256(canonical_json(payload)).hexdigest()
