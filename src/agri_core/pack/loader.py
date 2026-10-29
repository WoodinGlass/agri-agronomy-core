"""Load a pack directory into an immutable KnowledgeSet."""

from __future__ import annotations

import hashlib
import sqlite3
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from packaging.version import Version
from pydantic import BaseModel

from agri_core import __version__
from agri_core.models.dataset import DatasetRow
from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import (
    EnumSetValue,
    EnumValue,
    FactRow,
    RangeValue,
    ScalarValue,
    TrapezoidValue,
)
from agri_core.models.hazard import HazardRow
from agri_core.models.name import NameRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack.errors import (
    EngineTooOldError,
    InvalidPackError,
    PackDictionaryIncompatibleError,
    PackDuplicateKeyError,
    PackEnumInvalidError,
    PackError,
    PackFeatureUnsupportedError,
    PackFKViolationError,
    PackHashMismatchError,
    PackNotFoundError,
    PackPhaseInvalidError,
    PackSafetyViolationError,
    PackScopeInvalidError,
    PackShapeMismatchError,
    PackSyntheticNotAllowedError,
    PackTableInvalidError,
    PackTooLargeError,
    PackUnitMismatchError,
    PackUnknownParameterError,
    PackValueOutOfRangeError,
    UnsupportedSchemaVersionError,
)
from agri_core.pack.files import DEFAULT_MAX_BYTES, read_pack_bytes
from agri_core.pack.knowledge_set import (
    InMemoryKnowledgeSet,
    KnowledgeSet,
    SQLiteKnowledgeSet,
    _sqlite_uri,
)
from agri_core.pack.manifest import SUPPORTED_SCHEMA_VERSIONS, PackManifest
from agri_core.pack.sqlite_schema import SQLITE_SCHEMA_VERSION
from agri_core.pack.tables import TABLES, Table, read_table
from agri_core.pack.verify import hash_pack_files
from agri_core.registry.sources import SourceRow

_DEFAULT_DICTIONARY_SOURCE = "dictionary/parameters.core.yaml"
_MAX_FINDINGS = 20


def _default_dictionary() -> Dictionary:
    """Load the dictionary from packaged data, falling back to the repo source tree."""
    try:
        return Dictionary.load_packaged()
    except (FileNotFoundError, OSError):
        pass
    repo_root = Path(__file__).resolve().parents[3]
    source_path = repo_root / _DEFAULT_DICTIONARY_SOURCE
    if not source_path.is_file():
        raise PackError(
            f"cannot load dictionary: packaged _dictionary/ missing and "
            f"source fallback not found at {source_path}"
        )
    return Dictionary.load(source_path)


def parse_manifest_bytes(pack_toml: bytes) -> PackManifest:
    """Parse pack.toml bytes into a PackManifest; raise InvalidPackError on failure."""
    try:
        text = pack_toml.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidPackError(f"pack.toml is not valid UTF-8: {exc}", file="pack.toml") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidPackError(f"pack.toml is not valid TOML: {exc}", file="pack.toml") from exc
    try:
        return PackManifest.model_validate(data)
    except ValueError as exc:
        raise InvalidPackError(f"pack.toml is invalid: {exc}", file="pack.toml") from exc


def _check_compat(manifest: PackManifest, dictionary: Dictionary) -> None:
    if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"schema_version {manifest.schema_version} not in {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    engine = Version(__version__).base_version
    required_engine = Version(manifest.engine_min).base_version
    if Version(engine) < Version(required_engine):
        raise EngineTooOldError(
            f"engine {engine} < required {required_engine} (pack needs newer engine)"
        )
    have = Version(dictionary.version).base_version
    need = Version(manifest.dictionary_min).base_version
    if Version(have).major != Version(need).major:
        raise PackDictionaryIncompatibleError(
            f"dictionary MAJOR mismatch: have {have}, manifest requires {need}",
            key="dictionary_min",
        )
    if Version(have) < Version(need):
        raise PackDictionaryIncompatibleError(
            f"dictionary {have} < required {manifest.dictionary_min}",
            key="dictionary_min",
        )


def _load_tables(files: Mapping[str, bytes]) -> dict[str, Table]:
    tables: dict[str, Table] = {}
    for name in ("taxa", "names", "hazards", "datasets", "sources"):
        spec = TABLES[name]
        assert spec.filename is not None
        tables[name] = read_table(spec, files[spec.filename], source_name=spec.filename)
    for relpath in sorted(files):
        if not relpath.startswith("facts/"):
            continue
        tables[relpath] = read_table(TABLES["facts"], files[relpath], source_name=relpath)
    return tables


def _validate_rows(tables: Mapping[str, Table]) -> dict[str, list[object]]:
    model_for: dict[str, type[BaseModel]] = {
        "taxa": TaxonRow,
        "names": NameRow,
        "hazards": HazardRow,
        "datasets": DatasetRow,
        "sources": SourceRow,
    }
    out: dict[str, list[object]] = {
        "taxa": [],
        "names": [],
        "facts": [],
        "hazards": [],
        "datasets": [],
        "sources": [],
    }
    for name, model in model_for.items():
        table = tables[name]
        for row, line_num in zip(table.rows, table.line_numbers, strict=True):
            try:
                out[name].append(model.model_validate(dict(row)))
            except ValueError as exc:
                raise PackTableInvalidError(
                    f"{name}.csv line {line_num}: {exc}",
                    file=table.source_name,
                    line=line_num,
                ) from exc
    for relpath, table in tables.items():
        if not relpath.startswith("facts/"):
            continue
        for row, line_num in zip(table.rows, table.line_numbers, strict=True):
            try:
                out["facts"].append(FactRow.model_validate(dict(row)))
            except ValueError as exc:
                raise PackTableInvalidError(
                    f"{relpath} line {line_num}: {exc}",
                    file=relpath,
                    line=line_num,
                ) from exc
    return out


def _validate_structure(
    rows: dict[str, list[object]],
    tables: Mapping[str, Table],
    dictionary: Dictionary,
) -> list[PackError]:
    findings: list[PackError] = []

    def add(exc: PackError) -> None:
        if len(findings) < _MAX_FINDINGS:
            findings.append(exc)

    taxa: list[TaxonRow] = rows["taxa"]  # type: ignore[assignment]
    names: list[NameRow] = rows["names"]  # type: ignore[assignment]
    facts: list[FactRow] = rows["facts"]  # type: ignore[assignment]
    hazards: list[HazardRow] = rows["hazards"]  # type: ignore[assignment]
    sources: list[SourceRow] = rows["sources"]  # type: ignore[assignment]
    datasets: list[DatasetRow] = rows["datasets"]  # type: ignore[assignment]

    seen_taxa: set[str] = set()
    for t in taxa:
        if t.taxon_id in seen_taxa:
            add(PackDuplicateKeyError(f"duplicate taxon_id: {t.taxon_id}", key=t.taxon_id))
        seen_taxa.add(t.taxon_id)

    seen_facts: set[str] = set()
    for f in facts:
        if f.fact_id in seen_facts:
            add(PackDuplicateKeyError(f"duplicate fact_id: {f.fact_id}", key=f.fact_id))
        seen_facts.add(f.fact_id)

    taxon_ids = {t.taxon_id for t in taxa}
    source_ids = {s.id for s in sources}
    dataset_ids = {d.dataset_id for d in datasets}
    fact_ids = {f.fact_id for f in facts}
    taxon_by_id = {t.taxon_id: t for t in taxa}

    for t in taxa:
        if t.parent_id is not None:
            if t.parent_id == t.taxon_id:
                add(
                    PackFKViolationError(
                        f"parent_id == taxon_id: {t.taxon_id}",
                        key=t.taxon_id,
                    )
                )
            elif t.parent_id not in taxon_ids:
                add(
                    PackFKViolationError(
                        f"parent_id {t.parent_id} not in taxa",
                        key=t.taxon_id,
                    )
                )

    for n in names:
        if n.taxon_id not in taxon_ids:
            add(
                PackFKViolationError(
                    f"name.taxon_id {n.taxon_id} not in taxa",
                    file="names.csv",
                    key=n.taxon_id,
                )
            )
        for s in n.src or []:
            if s not in source_ids:
                add(
                    PackFKViolationError(
                        f"name.src {s} not in sources",
                        file="names.csv",
                        key=s,
                    )
                )
        if n.dataset_id is not None and n.dataset_id not in dataset_ids:
            add(
                PackFKViolationError(
                    f"name.dataset_id {n.dataset_id} not in datasets",
                    file="names.csv",
                    key=n.dataset_id,
                )
            )

    for h in hazards:
        if h.taxon_id not in taxon_ids:
            add(
                PackFKViolationError(
                    f"hazard.taxon_id {h.taxon_id} not in taxa",
                    file="hazards.csv",
                    key=h.taxon_id,
                )
            )
        for s in h.src or []:
            if s not in source_ids:
                add(
                    PackFKViolationError(
                        f"hazard.src {s} not in sources",
                        file="hazards.csv",
                        key=s,
                    )
                )
        if h.dataset_id is not None and h.dataset_id not in dataset_ids:
            add(
                PackFKViolationError(
                    f"hazard.dataset_id {h.dataset_id} not in datasets",
                    file="hazards.csv",
                    key=h.dataset_id,
                )
            )

    for f in facts:
        if f.taxon_id not in taxon_ids:
            add(
                PackFKViolationError(
                    f"fact.taxon_id {f.taxon_id} not in taxa",
                    key=f.fact_id,
                )
            )
            continue
        for s in f.src or []:
            if s not in source_ids:
                add(
                    PackFKViolationError(
                        f"fact.src {s} not in sources",
                        key=f.fact_id,
                    )
                )
        if f.dataset_id is not None and f.dataset_id not in dataset_ids:
            add(
                PackFKViolationError(
                    f"fact.dataset_id {f.dataset_id} not in datasets",
                    key=f.fact_id,
                )
            )
        if f.superseded_by is not None and f.superseded_by not in fact_ids:
            add(
                PackFKViolationError(
                    f"fact.superseded_by {f.superseded_by} not in facts",
                    key=f.fact_id,
                )
            )

        p = dictionary.parameters.get(f.parameter)
        if p is None:
            add(
                PackUnknownParameterError(
                    f"fact.parameter {f.parameter!r} not in dictionary",
                    key=f.fact_id,
                )
            )
            continue

        is_unknown = f.value.shape == "unknown"
        if not is_unknown and p.shape != f.value.shape:
            add(
                PackShapeMismatchError(
                    f"fact shape {f.value.shape!r} != parameter.shape {p.shape!r}",
                    key=f.fact_id,
                )
            )

        if (
            isinstance(f.value, (ScalarValue, RangeValue, TrapezoidValue))
            and p.unit is not None
            and f.value.unit != p.unit
        ):
            add(
                PackUnitMismatchError(
                    f"fact unit {f.value.unit!r} != parameter unit {p.unit!r}",
                    key=f.fact_id,
                )
            )

        if p.physical_range is not None:
            lo, hi = p.physical_range
            v = f.value
            if isinstance(v, ScalarValue):
                if not (lo <= v.value <= hi):
                    add(
                        PackValueOutOfRangeError(
                            f"value {v.value} outside physical_range [{lo}, {hi}]",
                            key=f.fact_id,
                        )
                    )
            elif isinstance(v, RangeValue):
                if not (lo <= v.min <= hi) or not (lo <= v.max <= hi):
                    add(
                        PackValueOutOfRangeError(
                            f"range [{v.min}, {v.max}] outside physical_range [{lo}, {hi}]",
                            key=f.fact_id,
                        )
                    )
            elif isinstance(v, TrapezoidValue) and not (lo <= min(v.pts) and max(v.pts) <= hi):
                add(
                    PackValueOutOfRangeError(
                        f"trapezoid pts {v.pts} outside physical_range [{lo}, {hi}]",
                        key=f.fact_id,
                    )
                )

        if isinstance(f.value, EnumValue) and p.enum_values and f.value.value not in p.enum_values:
            add(
                PackEnumInvalidError(
                    f"enum value {f.value.value!r} not in {p.enum_values}",
                    key=f.fact_id,
                )
            )

        if isinstance(f.value, EnumSetValue):
            if p.enum_source == "phases:biological":
                arch = taxon_by_id[f.taxon_id].archetype
                allowed = dictionary.phases_by_archetype.get(arch)
                if allowed is None:
                    add(
                        PackFeatureUnsupportedError(
                            f"phases_by_archetype not loaded; cannot validate {f.parameter}",
                            key=f.fact_id,
                        )
                    )
                else:
                    for val in f.value.values:
                        if val not in allowed:
                            add(
                                PackEnumInvalidError(
                                    f"enum_set value {val!r} not in {arch} phases {allowed}",
                                    key=f.fact_id,
                                )
                            )
            elif p.enum_values:
                for val in f.value.values:
                    if val not in p.enum_values:
                        add(
                            PackEnumInvalidError(
                                f"enum_set value {val!r} not in {p.enum_values}",
                                key=f.fact_id,
                            )
                        )

        if p.phase_set == "none":
            if f.phase is not None:
                add(
                    PackPhaseInvalidError(
                        f"phase_set=none but phase={f.phase!r}",
                        key=f.fact_id,
                    )
                )
        elif p.phase_set == "kc":
            if p.allowed_phases is None or f.phase not in p.allowed_phases:
                add(
                    PackPhaseInvalidError(
                        f"phase {f.phase!r} not allowed for kc",
                        key=f.fact_id,
                    )
                )
        elif p.phase_set == "biological":
            allowed = p.allowed_phases
            if allowed is None:
                arch = taxon_by_id[f.taxon_id].archetype
                allowed = dictionary.phases_by_archetype.get(arch, [])
            if f.phase not in allowed:
                add(
                    PackPhaseInvalidError(
                        f"phase {f.phase!r} not in biological phases {allowed}",
                        key=f.fact_id,
                    )
                )

        allowed_scope = set(p.scope_keys or [])
        extra = set(f.scope.keys()) - allowed_scope
        if extra:
            add(
                PackScopeInvalidError(
                    f"scope keys {sorted(extra)} not in {sorted(allowed_scope)}",
                    key=f.fact_id,
                )
            )

        if p.safety_class != "none" and f.status not in ("reviewed", "approved"):
            add(
                PackSafetyViolationError(
                    f"safety_class={p.safety_class} requires reviewed/approved, got {f.status!r}",
                    key=f.fact_id,
                )
            )

    for relpath, table in tables.items():
        if not relpath.startswith("facts/"):
            continue
        expected_tid = relpath[len("facts/") : -len(".csv")]
        for row, line_num in zip(table.rows, table.line_numbers, strict=True):
            if row["taxon_id"] != expected_tid:
                add(
                    PackFKViolationError(
                        f"row in {relpath} has taxon_id={row['taxon_id']!r}, "
                        f"expected {expected_tid!r}",
                        file=relpath,
                        line=line_num,
                    )
                )

    return findings


def load_knowledge_set_from_files(
    files: Mapping[str, bytes],
    *,
    allow_synthetic: bool = False,
    expected_hash: str | None = None,
    dictionary: Dictionary | None = None,
) -> KnowledgeSet:
    """Load a KnowledgeSet from an in-memory allowlist dict (read_pack_bytes output)."""
    if dictionary is None:
        dictionary = _default_dictionary()

    manifest = parse_manifest_bytes(files["pack.toml"])
    if (
        manifest.artifact_sha256 is not None
        or manifest.sqlite_schema_version is not None
        or manifest.built_by is not None
    ):
        raise InvalidPackError(
            "source pack.toml declares build-only fields "
            "(artifact_sha256 / sqlite_schema_version / built_by); "
            "these appear only in built manifests. Did you copy a built "
            "pack.toml onto a source tree?"
        )

    actual = hash_pack_files(files)
    if manifest.content_hash is not None and manifest.content_hash != actual:
        raise PackHashMismatchError(
            f"content_hash mismatch: manifest={manifest.content_hash} "
            f"computed={actual}. If you changed this pack, run "
            f"`agri-core pack lock`.",
            file="pack.toml",
        )
    if expected_hash is not None and expected_hash != actual:
        raise PackHashMismatchError(
            f"expected_hash mismatch: caller={expected_hash} computed={actual}",
            file="pack.toml",
        )
    verified = manifest.content_hash is not None or expected_hash is not None

    _check_compat(manifest, dictionary)

    if manifest.synthetic and not allow_synthetic:
        raise PackSyntheticNotAllowedError(
            "pack is synthetic; load with allow_synthetic=True",
            file="pack.toml",
        )

    adv_bytes = files.get("advisories.csv")
    if adv_bytes is not None and adv_bytes.strip():
        raise PackFeatureUnsupportedError(
            "advisories.csv has non-whitespace content; unsupported until M8",
            file="advisories.csv",
        )

    tables = _load_tables(files)
    rows = _validate_rows(tables)

    findings = _validate_structure(rows, tables, dictionary)
    if findings:
        first = findings[0]
        raise type(first)(
            str(first),
            file=first.file,
            line=first.line,
            key=first.key,
            findings=tuple(findings),
        )

    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash=actual,
        dictionary_version=dictionary.version,
        dictionary=dictionary,
        verified=verified,
        taxa=rows["taxa"],  # type: ignore[arg-type]
        names=rows["names"],  # type: ignore[arg-type]
        facts=rows["facts"],  # type: ignore[arg-type]
        hazards=rows["hazards"],  # type: ignore[arg-type]
        sources=rows["sources"],  # type: ignore[arg-type]
        datasets=rows["datasets"],  # type: ignore[arg-type]
    )


def _detect_pack_kind(root: Path) -> Literal["source", "built"]:
    """Detect pack kind from directory contents.

    Built pack:  ``pack.sqlite`` + ``pack.toml``.
    Source pack: ``taxa.csv`` + ``pack.toml``.
    Both or neither: ``InvalidPackError``.
    """
    has_sqlite = (root / "pack.sqlite").is_file()
    has_taxa = (root / "taxa.csv").is_file()
    if has_sqlite and has_taxa:
        raise InvalidPackError(
            f"{root} contains both pack.sqlite and taxa.csv; cannot tell source from built pack"
        )
    if has_sqlite:
        return "built"
    if has_taxa:
        return "source"
    raise InvalidPackError(f"{root} contains neither pack.sqlite nor taxa.csv; not a pack")


def _check_built_metadata(
    pack_sqlite: Path,
    manifest: PackManifest,
    *,
    schema_version: int,
    content_hash: str,
    built_by: str,
) -> None:
    """Verify pack.toml and SQLite metadata agree on 8 rows + user_version."""
    conn = sqlite3.connect(_sqlite_uri(pack_sqlite), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        uv = conn.execute("PRAGMA user_version").fetchone()[0]
        if uv != schema_version:
            raise InvalidPackError(
                f"sqlite user_version {uv} != manifest sqlite_schema_version {schema_version}",
                file="pack.sqlite",
            )
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM metadata")}
    finally:
        conn.close()

    expected = {
        "name": manifest.name,
        "version": manifest.version,
        "schema_version": str(manifest.schema_version),
        "engine_min": manifest.engine_min,
        "dictionary_min": manifest.dictionary_min,
        "synthetic": "1" if manifest.synthetic else "0",
        "content_hash": content_hash,
        "built_by": built_by,
    }
    for key, expected_val in expected.items():
        actual = rows.get(key)
        if actual != expected_val:
            raise InvalidPackError(
                f"metadata mismatch for {key!r}: sqlite={actual!r} manifest={expected_val!r}",
                file="pack.sqlite",
            )


def _load_built_pack(
    root: Path,
    *,
    allow_synthetic: bool,
    expected_hash: str | None,
    dictionary: Dictionary | None,
    max_bytes: int,
) -> KnowledgeSet:
    """Load a built pack (pack.sqlite + pack.toml) into a SQLiteKnowledgeSet."""
    pack_toml = root / "pack.toml"
    pack_sqlite = root / "pack.sqlite"
    if not pack_toml.is_file():
        raise InvalidPackError(f"pack.toml not found in {root}", file="pack.toml")
    if not pack_sqlite.is_file():
        raise InvalidPackError(f"pack.sqlite not found in {root}", file="pack.sqlite")
    if pack_toml.is_symlink() or pack_sqlite.is_symlink():
        raise InvalidPackError(f"symlinks not allowed in built pack: {root}")

    total = pack_toml.stat().st_size + pack_sqlite.stat().st_size
    if total > max_bytes:
        raise PackTooLargeError(
            f"built pack size {total} > max_bytes {max_bytes}",
            file=str(root),
        )

    manifest = parse_manifest_bytes(pack_toml.read_bytes())

    schema_version = manifest.sqlite_schema_version
    artifact_sha256 = manifest.artifact_sha256
    content_hash = manifest.content_hash
    built_by = manifest.built_by
    if schema_version is None or artifact_sha256 is None or built_by is None:
        raise InvalidPackError(
            "built pack.toml must declare artifact_sha256, sqlite_schema_version, "
            "and built_by (all-or-none)",
            file="pack.toml",
        )
    if content_hash is None:
        raise InvalidPackError("built pack.toml must declare content_hash", file="pack.toml")

    if schema_version != SQLITE_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"built pack sqlite_schema_version {schema_version} "
            f"!= engine SQLITE_SCHEMA_VERSION {SQLITE_SCHEMA_VERSION}"
        )

    # Hash the artifact in fixed-size chunks instead of reading the whole
    # file into memory as a single allocation. Digest is identical. This
    # does not reduce ru_maxrss peak for the current 55 MB sample pack
    # (dominated by the import baseline), but it is safe for larger
    # packs: real agri-knowledge artifacts can be hundreds of MB, where
    # ``read_bytes`` would either spike RSS or fail allocation outright.
    _h = hashlib.sha256()
    with pack_sqlite.open("rb") as _f:
        while True:
            _chunk = _f.read(1 << 20)  # 1 MiB
            if not _chunk:
                break
            _h.update(_chunk)
    actual_artifact = "sha256:" + _h.hexdigest()
    if artifact_sha256 != actual_artifact:
        raise PackHashMismatchError(
            f"artifact_sha256 mismatch: manifest={artifact_sha256} computed={actual_artifact}",
            file="pack.sqlite",
        )
    if expected_hash is not None and expected_hash != actual_artifact:
        raise PackHashMismatchError(
            f"expected_hash mismatch: caller={expected_hash} computed={actual_artifact}",
            file="pack.sqlite",
        )

    if dictionary is None:
        dictionary = _default_dictionary()
    _check_compat(manifest, dictionary)

    if manifest.synthetic and not allow_synthetic:
        raise PackSyntheticNotAllowedError(
            "pack is synthetic; load with allow_synthetic=True",
            file="pack.toml",
        )

    _check_built_metadata(
        pack_sqlite,
        manifest,
        schema_version=schema_version,
        content_hash=content_hash,
        built_by=built_by,
    )

    return SQLiteKnowledgeSet._build(
        sqlite_path=pack_sqlite,
        manifest=manifest,
        pack_hash=content_hash,
        dictionary_version=dictionary.version,
        dictionary=dictionary,
        verified=True,
    )


def load_knowledge_set(
    path: str | Path,
    *,
    allow_synthetic: bool = False,
    expected_hash: str | None = None,
    dictionary: Dictionary | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> KnowledgeSet:
    """Load a pack directory into an immutable KnowledgeSet.

    The pack kind is detected from directory contents:

    - ``pack.sqlite`` + ``pack.toml`` (built pack) → SQLite backend.
      ``expected_hash`` compares against ``artifact_sha256`` (the SQLite
      file hash), because ``content_hash`` cannot be recomputed from the
      built artifact alone.
    - ``taxa.csv`` + ``pack.toml`` (source pack) → CSV backend.
      ``expected_hash`` compares against ``content_hash``.

    Exactly one of the two layouts must be present. Having both or neither
    raises ``InvalidPackError``.
    """
    root = Path(path)
    if not root.exists():
        raise PackNotFoundError(f"pack directory not found: {root}")
    if not root.is_dir():
        raise InvalidPackError(f"not a directory: {root}", file=str(root))

    kind = _detect_pack_kind(root)
    if kind == "built":
        return _load_built_pack(
            root,
            allow_synthetic=allow_synthetic,
            expected_hash=expected_hash,
            dictionary=dictionary,
            max_bytes=max_bytes,
        )

    files = read_pack_bytes(root, max_bytes=max_bytes)
    return load_knowledge_set_from_files(
        files,
        allow_synthetic=allow_synthetic,
        expected_hash=expected_hash,
        dictionary=dictionary,
    )


__all__ = [
    "load_knowledge_set",
    "load_knowledge_set_from_files",
    "parse_manifest_bytes",
]
