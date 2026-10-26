"""In-memory dictionary of parameters (v1.0.0)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

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
    phases_by_archetype: dict[str, list[str]] = {}

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        return check_semver(v)

    @classmethod
    def load(cls, path: Path) -> Dictionary:
        """Load from an explicit path.

        Also reads sibling ``vocab/phases_by_archetype.yaml`` if present.
        """
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        phases = _try_load_phases_by_archetype(path.parent / "vocab" / "phases_by_archetype.yaml")
        return cls._from_data(data, phases_by_archetype=phases)

    @classmethod
    def load_packaged(cls) -> Dictionary:
        """Load the dictionary bundled inside the installed package."""
        from importlib.resources import files as _files

        pkg_dir = _files("agri_core") / "_dictionary"
        text = (pkg_dir / "parameters.core.yaml").read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        phases = _try_load_phases_by_archetype(pkg_dir / "vocab" / "phases_by_archetype.yaml")
        return cls._from_data(data, phases_by_archetype=phases)

    @classmethod
    def _from_data(
        cls,
        data: dict[str, Any],
        *,
        phases_by_archetype: dict[str, list[str]] | None = None,
    ) -> Dictionary:
        params: dict[str, ParameterDef] = {}
        raw_params = data.get("parameters") or {}
        for key, raw in raw_params.items():
            if not re.match(r"^[a-z][a-z0-9_]*$", key):
                raise ValueError(f"parameter key {key!r} not snake_case")
            if key in params:
                raise ValueError(f"parameter key {key!r} duplicated")
            merged = {"key": key, **raw}
            params[key] = ParameterDef.model_validate(merged)
        return cls(
            version=data["dictionary_version"],
            parameters=params,
            phases_by_archetype=phases_by_archetype or {},
        )

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


def _try_load_phases_by_archetype(
    path: Path | Traversable,
) -> dict[str, list[str]]:
    """Load {archetype: [phases]} from a phases_by_archetype.yaml, or {} if missing."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError):
        return {}
    raw = data.get("phases_by_archetype") or {}
    out: dict[str, list[str]] = {}
    for arch, entry in raw.items():
        if isinstance(entry, dict) and "phases" in entry:
            phases = entry["phases"]
            if isinstance(phases, list):
                out[arch] = list(phases)
    return out


def load_bundle_from_root(root: Path) -> dict[str, Any]:
    """Load ``{version, parameters, vocab, units}`` from a dictionary root.

    ``root`` must contain ``parameters.core.yaml``, ``unit_registry.yaml`` and
    a ``vocab/`` directory of YAML files. All vocab files are parsed and
    included; the resulting dict is the input for ``contract_hash`` and for
    the history snapshots.
    """
    params_data = yaml.safe_load((root / "parameters.core.yaml").read_text(encoding="utf-8"))
    units_data = yaml.safe_load((root / "unit_registry.yaml").read_text(encoding="utf-8"))
    vocab: dict[str, Any] = {}
    for f in sorted((root / "vocab").glob("*.yaml")):
        vocab[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8"))
    return {
        "version": params_data["dictionary_version"],
        "parameters": params_data["parameters"],
        "vocab": vocab,
        "units": units_data,
    }


def contract_hash(bundle: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON of ``{parameters, vocab, units}``.

    Version is intentionally excluded: the version + hash pair lives in
    ``dictionary.lock`` and is checked separately. Two bundles with the same
    content but different version strings have the same ``contract_hash``.
    """
    payload = {
        "parameters": bundle["parameters"],
        "vocab": bundle["vocab"],
        "units": bundle["units"],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


_SOFT_FIELDS: frozenset[str] = frozenset({"description", "rationale"})
_WIDENABLE_FIELDS: frozenset[str] = frozenset(
    {
        "applies_to",
        "scope_keys",
        "allowed_phases",
        "physical_range",
    }
)


def _narrowed(old: list[str] | None, new: list[str] | None) -> bool:
    """True if new is a strict narrowing of old (removed values, or from unlimited)."""
    if old is None:
        return new is not None
    if new is None:
        return False
    return not set(new).issuperset(set(old))


def _widened(old: list[str] | None, new: list[str] | None) -> bool:
    """True if new is a widening of old (added values, or to unlimited)."""
    if old is None:
        return False
    if new is None:
        return True
    return bool(set(new) - set(old))


def _range_narrowed(
    old: tuple[float, float] | list[float] | None,
    new: tuple[float, float] | list[float] | None,
) -> bool:
    if old is None:
        return new is not None
    if new is None:
        return False
    return new[0] > old[0] or new[1] < old[1]


def _range_widened(
    old: tuple[float, float] | list[float] | None,
    new: tuple[float, float] | list[float] | None,
) -> bool:
    if old is None:
        return False
    if new is None:
        return True
    return new[0] < old[0] or new[1] > old[1]


_APPLIES_TO_DIMS: tuple[str, ...] = (
    "organism_groups",
    "archetypes",
    "uses",
    "systems",
    "traits",
)


def classify_change(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Classify the SemVer bump required by a bundle change.

    Returns ``"MAJOR"``, ``"MINOR"`` or ``"PATCH"``. Fail-closed: any change
    that is not explicitly classified as a PATCH or a known MINOR pattern is
    MAJOR.

    MAJOR: key removed or renamed; shape, unit, phase_set, enum_values,
    enum_source, or safety_class changed; applies_to, scope_keys,
    allowed_phases, or physical_range narrowed; tier_required false -> true;
    vocab value removed; custom unit definition changed or removed; any other
    non-soft field changed.

    MINOR: new key; applies_to, scope_keys, allowed_phases, or physical_range
    widened; new vocab value; new custom unit.

    PATCH: only description or rationale changed.
    """
    old_p = old["parameters"]
    new_p = new["parameters"]

    # --- MAJOR checks ---
    if set(old_p) - set(new_p):
        return "MAJOR"

    for key in old_p:
        op = old_p[key]
        np_ = new_p[key]

        for field in ("shape", "unit", "phase_set", "enum_values", "enum_source", "safety_class"):
            if op.get(field) != np_.get(field):
                return "MAJOR"

        if op.get("tier_required") is False and np_.get("tier_required") is True:
            return "MAJOR"

        oa = op.get("applies_to") or {}
        na = np_.get("applies_to") or {}
        for dim in _APPLIES_TO_DIMS:
            if _narrowed(oa.get(dim), na.get(dim)):
                return "MAJOR"

        if _narrowed(op.get("scope_keys") or [], np_.get("scope_keys") or []):
            return "MAJOR"
        if _narrowed(op.get("allowed_phases"), np_.get("allowed_phases")):
            return "MAJOR"
        if _range_narrowed(op.get("physical_range"), np_.get("physical_range")):
            return "MAJOR"

    for vname, ovocab in (old.get("vocab") or {}).items():
        nvocab = (new.get("vocab") or {}).get(vname)
        if nvocab is None:
            return "MAJOR"
        for section, ometa in ovocab.items():
            if section == "schema_version" or not isinstance(ometa, dict):
                continue
            nmeta = nvocab.get(section)
            if not isinstance(nmeta, dict):
                if ometa:
                    return "MAJOR"
                continue
            if set(ometa) - set(nmeta):
                return "MAJOR"

    ou = (old.get("units") or {}).get("custom_units") or {}
    nu = (new.get("units") or {}).get("custom_units") or {}
    for unit, odef in ou.items():
        if unit not in nu or nu[unit] != odef:
            return "MAJOR"

    # Fail-closed: any non-soft field change not caught above is MAJOR
    for key in old_p:
        op = old_p[key]
        np_ = new_p[key]
        for field in set(op) | set(np_):
            if field in _SOFT_FIELDS or field in _WIDENABLE_FIELDS:
                continue
            if op.get(field) != np_.get(field):
                return "MAJOR"

    # --- MINOR checks ---
    if set(new_p) - set(old_p):
        return "MINOR"

    for key in old_p:
        op = old_p[key]
        np_ = new_p[key]
        oa = op.get("applies_to") or {}
        na = np_.get("applies_to") or {}
        for dim in _APPLIES_TO_DIMS:
            if _widened(oa.get(dim), na.get(dim)):
                return "MINOR"
        if _widened(op.get("scope_keys") or [], np_.get("scope_keys") or []):
            return "MINOR"
        if _widened(op.get("allowed_phases"), np_.get("allowed_phases")):
            return "MINOR"
        if _range_widened(op.get("physical_range"), np_.get("physical_range")):
            return "MINOR"

    for vname, ovocab in (old.get("vocab") or {}).items():
        nvocab = (new.get("vocab") or {}).get(vname) or {}
        for section, ometa in ovocab.items():
            if section == "schema_version" or not isinstance(ometa, dict):
                continue
            nmeta = nvocab.get(section)
            if isinstance(nmeta, dict) and (set(nmeta) - set(ometa)):
                return "MINOR"

    if set(nu) - set(ou):
        return "MINOR"

    return "PATCH"
