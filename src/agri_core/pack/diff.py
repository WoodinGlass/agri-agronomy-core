"""Pack diff: compare two loaded packs (M7-6).

Read-only. Determines whether a change to a pack respects the identity
invariants from M6:

- Fact IDs are never reused. A fact whose ``value``, ``scope``,
  ``parameter``, ``taxon_id`` or ``phase`` changes must be a new
  ``fact_id`` with ``superseded_by`` pointing at the old one.
- Facts and taxa are never deleted. Removing one is a violation.
- Status, evidence, review metadata, source references, and the
  ``superseded_by`` pointer may change in place.

Everything else (added taxa, added facts, metadata changes) is a
normal difference. ``--exit-code`` promotes normal differences to
exit 1 for CI; violations are always exit 1.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from agri_core.models.fact import FactRow
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import KnowledgeSet

__all__ = [
    "DiffReport",
    "DiffViolation",
    "FactChange",
    "FactChangeClass",
    "TaxaDiff",
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

    kind: Literal["taxon_removed", "fact_removed", "fact_id_reused"]
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
        classification = (
            FactChangeClass.VIOLATION
            if any(f in _VIOLATION_FIELDS for f in changed)
            else FactChangeClass.ACCEPTABLE
        )
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
