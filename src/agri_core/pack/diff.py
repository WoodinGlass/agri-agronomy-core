"""Pack diff: compare two loaded packs (M7-6).

Read-only. Determines whether a change to a pack respects the identity
invariants from M6:

- Fact IDs are never reused. A fact whose ``value``, ``scope``,
  ``parameter``, ``taxon_id`` or ``phase`` changes must be a new
  ``fact_id`` with ``superseded_by`` pointing at the old one —
  **unless the old status was ``draft`` or ``imported``**: those
  are still under editorial control and their content fields may
  change in place.
- Facts and taxa are never deleted. Removing one is a violation.
- Status, evidence, review metadata, source references, and the
  ``superseded_by`` pointer may change in place.

Everything else (added taxa, added facts, metadata changes) is a
normal difference. ``--exit-code`` promotes normal differences to
exit 1 for CI; violations are always exit 1.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from agri_core.models.fact import FactRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import KnowledgeSet

if TYPE_CHECKING:
    from agri_core.pack.manifest import PackManifest


def _detect_native_diff() -> Any:
    """Return the native diff adapter if the extension was built with exp-diff."""
    try:
        from agri_core import _native as _native_mod
    except ImportError:
        return None
    return getattr(_native_mod, "diff_pack_paths", None)


_native_diff_pack_paths: Any = _detect_native_diff()
_DIFF_NATIVE: bool = _native_diff_pack_paths is not None

__all__ = [
    "DiffReport",
    "DiffViolation",
    "FactChange",
    "FactChangeClass",
    "TaxaDiff",
    "diff_pack_paths",
    "diff_packs",
]


_ACCEPTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "evidence",
        "reviewed_by",
        "reviewed_at",
        "locator",
        "superseded_by",
        "src",
        "dataset_id",
        "provenance_kind",
    }
)
_VIOLATION_FIELDS: frozenset[str] = frozenset({"value", "scope", "parameter", "taxon_id", "phase"})


_REVIEWED_STATUSES: frozenset[str] = frozenset({"reviewed", "approved"})
"""Statuses at which a fact's content is frozen. Once a fact reaches one
of these, changing content fields requires a new ``fact_id`` +
``superseded_by``. ``draft`` and ``imported`` facts remain editable."""


def _classify_fact_change(old_status: str, changed: tuple[str, ...]) -> FactChangeClass:
    """Classify a fact change as violation or acceptable.

    A change to ``value``, ``scope``, ``parameter``, ``taxon_id``, or
    ``phase`` is a violation only if the OLD status was ``reviewed`` or
    ``approved``. Once a fact is reviewed its content is frozen, and
    changing it requires a new ``fact_id`` with ``superseded_by``.
    ``draft`` and ``imported`` facts are still under editorial control;
    their content fields may change in place.
    """
    if old_status not in _REVIEWED_STATUSES:
        return FactChangeClass.ACCEPTABLE
    if any(f in _VIOLATION_FIELDS for f in changed):
        return FactChangeClass.VIOLATION
    return FactChangeClass.ACCEPTABLE


class FactChangeClass(StrEnum):
    """Whether a fact change respects the never-reused identity invariant."""

    ACCEPTABLE = "acceptable"
    VIOLATION = "violation"


class FactChange(BaseModel):
    """A fact that exists in both packs with at least one changed field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    fields_changed: tuple[str, ...]
    classification: FactChangeClass
    old_status: str
    new_status: str


class TaxaDiff(BaseModel):
    """Taxa added, removed, or changed between old and new."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()


class DiffViolation(BaseModel):
    """A change that violates an M6 identity invariant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[
        "taxon_removed",
        "fact_removed",
        "fact_id_reused",
        "id_removed_from_ledger",
    ]
    entity_id: str
    message: str


class DiffReport(BaseModel):
    """Structured diff between two packs. Deterministic; JSON-safe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    old_pack_hash: str
    new_pack_hash: str
    identical: bool
    taxa: TaxaDiff
    facts_added: tuple[str, ...] = ()
    facts_removed: tuple[str, ...] = ()
    facts_changed: tuple[FactChange, ...] = ()
    violations: tuple[DiffViolation, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ok(self) -> bool:
        """True when there are no violations (differences may still exist)."""
        return not self.violations


def _diff_config_args() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Pass field-set constants to native adapters (HP#6)."""
    return _ACCEPTABLE_FIELDS, _VIOLATION_FIELDS, _REVIEWED_STATUSES


def _render_fact_change(fc: dict[str, Any]) -> FactChange:
    """Translate a native FactChange payload to the Python contract."""
    return FactChange(
        fact_id=fc["fact_id"],
        fields_changed=tuple(fc["fields_changed"]),
        classification=FactChangeClass(fc["classification"]),
        old_status=fc["old_status"],
        new_status=fc["new_status"],
    )


def _render_violation(v: dict[str, Any]) -> DiffViolation:
    """Translate a native ViolationMeta payload to DiffViolation (N17)."""
    kind = v["kind"]
    entity_id = v["entity_id"]
    meta = v.get("meta")
    if kind == "fact_id_reused":
        fields = list(meta["fields_changed"]) if meta else []
        message = f"fact {entity_id} changed {fields}; create a new fact_id and set superseded_by"
    elif kind == "taxon_removed":
        message = f"taxon {entity_id} removed; taxon_ids are never reused"
    elif kind == "fact_removed":
        message = f"fact {entity_id} removed; set superseded_by instead"
    elif kind == "id_removed_from_ledger":
        message = f"taxon ID {entity_id!r} removed from ids.lock; append-only (ADR-011)"
    else:
        raise ValueError(f"unknown violation kind: {kind!r}")
    return DiffViolation(kind=kind, entity_id=entity_id, message=message)


def _render_diff_payload(payload: dict[str, Any]) -> DiffReport:
    """Translate the native DiffOutcome dict into the Python contract."""
    return DiffReport(
        old_pack_hash=payload["old_pack_hash"],
        new_pack_hash=payload["new_pack_hash"],
        identical=payload["identical"],
        taxa=TaxaDiff(
            added=tuple(payload["taxa_added"]),
            removed=tuple(payload["taxa_removed"]),
            changed=tuple(payload["taxa_changed"]),
        ),
        facts_added=tuple(payload["facts_added"]),
        facts_removed=tuple(payload["facts_removed"]),
        facts_changed=tuple(_render_fact_change(fc) for fc in payload["facts_changed"]),
        violations=tuple(_render_violation(v) for v in payload["violations"]),
    )


def _get(row: FactRow, name: str) -> Any:
    return getattr(row, name)


def _diff_fact_fields(old: FactRow, new: FactRow) -> tuple[str, ...]:
    all_fields = _ACCEPTABLE_FIELDS | _VIOLATION_FIELDS
    changed = [n for n in all_fields if _get(old, n) != _get(new, n)]
    return tuple(sorted(changed))


def _facts_by_id(ks: KnowledgeSet) -> dict[str, FactRow]:
    return {f.fact_id: f for f in ks.facts()}


def _taxa_by_id(ks: KnowledgeSet) -> dict[str, TaxonRow]:
    return {t.taxon_id: t for t in ks.taxa()}


def diff_packs(old: KnowledgeSet, new: KnowledgeSet) -> DiffReport:
    """Compare two loaded packs. Deterministic; safe to call repeatedly."""
    old_taxa = _taxa_by_id(old)
    new_taxa = _taxa_by_id(new)
    old_facts = _facts_by_id(old)
    new_facts = _facts_by_id(new)

    taxa_added = tuple(sorted(new_taxa.keys() - old_taxa.keys()))
    taxa_removed = tuple(sorted(old_taxa.keys() - new_taxa.keys()))
    taxa_changed = tuple(
        sorted(tid for tid in (old_taxa.keys() & new_taxa.keys()) if old_taxa[tid] != new_taxa[tid])
    )

    facts_added = tuple(sorted(new_facts.keys() - old_facts.keys()))
    facts_removed = tuple(sorted(old_facts.keys() - new_facts.keys()))

    facts_changed: list[FactChange] = []
    violations: list[DiffViolation] = []

    for fid in sorted(old_facts.keys() & new_facts.keys()):
        of, nf = old_facts[fid], new_facts[fid]
        if of == nf:
            continue
        changed = _diff_fact_fields(of, nf)
        if not changed:
            continue
        classification = _classify_fact_change(str(of.status), changed)
        facts_changed.append(
            FactChange(
                fact_id=fid,
                fields_changed=changed,
                classification=classification,
                old_status=str(of.status),
                new_status=str(nf.status),
            )
        )
        if classification == FactChangeClass.VIOLATION:
            violations.append(
                DiffViolation(
                    kind="fact_id_reused",
                    entity_id=fid,
                    message=(
                        f"fact {fid} changed {list(changed)}; "
                        f"create a new fact_id and set superseded_by"
                    ),
                )
            )

    for tid in taxa_removed:
        violations.append(
            DiffViolation(
                kind="taxon_removed",
                entity_id=tid,
                message=f"taxon {tid} removed; taxon_ids are never reused",
            )
        )
    for fid in facts_removed:
        violations.append(
            DiffViolation(
                kind="fact_removed",
                entity_id=fid,
                message=f"fact {fid} removed; set superseded_by instead",
            )
        )

    identical = (
        not taxa_added
        and not taxa_removed
        and not taxa_changed
        and not facts_added
        and not facts_removed
        and not facts_changed
    )

    # ADR-011: ids.lock is append-only. If both sides expose it, IDs
    # removed from the ledger are violations. Built packs don't preserve
    # ids.lock, so comparison is skipped when either side returns None.
    old_lock = old.ids_lock()
    new_lock = new.ids_lock()
    if old_lock is not None and new_lock is not None:
        for tid in sorted(old_lock - new_lock):
            violations.append(
                DiffViolation(
                    kind="id_removed_from_ledger",
                    entity_id=tid,
                    message=(f"taxon ID {tid!r} removed from ids.lock; append-only (ADR-011)"),
                )
            )

    return DiffReport(
        old_pack_hash=old.pack_hash,
        new_pack_hash=new.pack_hash,
        identical=identical,
        taxa=TaxaDiff(added=taxa_added, removed=taxa_removed, changed=taxa_changed),
        facts_added=facts_added,
        facts_removed=facts_removed,
        facts_changed=tuple(facts_changed),
        violations=tuple(sorted(violations, key=lambda v: (v.kind, v.entity_id))),
    )


def diff_pack_paths(
    old_path: Path,
    new_path: Path,
    *,
    old_manifest: PackManifest,
    new_manifest: PackManifest,
) -> DiffReport:
    """Diff two packs by path when the native adapter is present.

    Native path requires ``exp-diff`` at build time (detected via
    ``_DIFF_NATIVE``) and a ``pack.sqlite`` in both directories.
    Otherwise falls back to :func:`diff_packs`.
    """
    old_sqlite = old_path / "pack.sqlite"
    new_sqlite = new_path / "pack.sqlite"
    if (
        _DIFF_NATIVE
        and _native_diff_pack_paths is not None
        and old_sqlite.is_file()
        and new_sqlite.is_file()
    ):
        acceptable, violation, protected = _diff_config_args()
        raw = _native_diff_pack_paths(
            str(old_sqlite),
            old_manifest.model_dump(mode="json"),
            str(new_sqlite),
            new_manifest.model_dump(mode="json"),
            acceptable,
            violation,
            protected,
        )
        return _render_diff_payload(raw)
    from agri_core.pack import load_knowledge_set as _load

    return diff_packs(
        _load(old_path, allow_synthetic=True),
        _load(new_path, allow_synthetic=True),
    )
