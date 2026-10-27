"""Tier derivation from a KnowledgeSet (M7-5)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow
from agri_core.models.parameter import ParameterDef
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import KnowledgeSet

__all__ = ["Tier", "TierResult", "derive_all_tiers", "derive_tier"]


class Tier(StrEnum):
    """Ordered tier of a taxon's data coverage."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


_STATUS_ORDER: dict[str, int] = {
    "imported": 0,
    "draft": 1,
    "reviewed": 2,
    "approved": 3,
}
_T2_MIN = "reviewed"
_T3_MIN = "approved"


class TierResult(BaseModel):
    """Outcome of ``derive_tier``. Frozen; JSON-safe; deterministic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    taxon_id: str
    tier: Tier
    required_params: tuple[str, ...] = ()
    missing_params: tuple[str, ...] = ()
    system_gaps: tuple[str, ...] = ()
    detail: str = ""


def _matches_taxon(param: ParameterDef, taxon: TaxonRow) -> bool:
    a = param.applies_to
    if a.organism_groups and taxon.organism_group not in a.organism_groups:
        return False
    if a.archetypes and taxon.archetype not in a.archetypes:
        return False
    return not (a.uses and not any(u in a.uses for u in taxon.uses))


def _has_systems(param: ParameterDef) -> bool:
    return bool(param.applies_to.systems)


def _phases_for(param: ParameterDef, taxon: TaxonRow, dictionary: Dictionary) -> list[str] | None:
    if param.phase_set == "none":
        return None
    if param.phase_set == "kc":
        return list(param.allowed_phases or [])
    if param.phase_set == "biological":
        if param.allowed_phases:
            return list(param.allowed_phases)
        return list(dictionary.phases_by_archetype.get(taxon.archetype, []))
    return None


def _meets(fact: FactRow, min_status: str) -> bool:
    return _STATUS_ORDER.get(fact.status, -1) >= _STATUS_ORDER.get(min_status, 999)


def _param_satisfied(
    param: ParameterDef,
    taxon: TaxonRow,
    live_facts: list[FactRow],
    dictionary: Dictionary,
    min_status: str,
) -> bool:
    phases = _phases_for(param, taxon, dictionary)
    if phases is None:
        matches = [f for f in live_facts if f.parameter == param.key]
        return any(_meets(f, min_status) for f in matches)
    for phase in phases:
        matches = [f for f in live_facts if f.parameter == param.key and f.phase == phase]
        if not any(_meets(f, min_status) for f in matches):
            return False
    return True


def derive_tier(ks: KnowledgeSet, taxon_id: str, dictionary: Dictionary) -> TierResult:
    taxon = ks.taxon(taxon_id)
    taxon_facts = [f for f in ks.facts() if f.taxon_id == taxon_id]
    live_facts = [f for f in taxon_facts if f.superseded_by is None]

    if not live_facts:
        return TierResult(taxon_id=taxon_id, tier=Tier.T0, detail="no live facts")

    required: list[str] = []
    system_gaps: list[str] = []
    for key in sorted(dictionary.parameters):
        param = dictionary.parameters[key]
        if not _matches_taxon(param, taxon):
            continue
        if _has_systems(param):
            present = any(f.parameter == key for f in live_facts)
            if not present:
                system_gaps.append(key)
            continue
        if param.tier_required:
            required.append(key)

    required_t = tuple(required)
    system_gaps_t = tuple(sorted(system_gaps))

    missing_t2: list[str] = []
    for key in required:
        param = dictionary.parameters[key]
        if not _param_satisfied(param, taxon, live_facts, dictionary, _T2_MIN):
            missing_t2.append(key)

    if missing_t2:
        return TierResult(
            taxon_id=taxon_id,
            tier=Tier.T1,
            required_params=required_t,
            missing_params=tuple(sorted(missing_t2)),
            system_gaps=system_gaps_t,
            detail=f"missing at T2: {len(missing_t2)} of {len(required)}",
        )

    missing_t3: list[str] = []
    for key in required:
        param = dictionary.parameters[key]
        if not _param_satisfied(param, taxon, live_facts, dictionary, _T3_MIN):
            missing_t3.append(key)
    for f in live_facts:
        fact_param = dictionary.parameters.get(f.parameter)
        if fact_param is None or fact_param.safety_class == "none":
            continue
        if f.status != "approved" or len(f.reviewed_by or []) < 2:
            missing_t3.append(f.parameter)

    if missing_t3:
        return TierResult(
            taxon_id=taxon_id,
            tier=Tier.T2,
            required_params=required_t,
            missing_params=tuple(sorted(set(missing_t3))),
            system_gaps=system_gaps_t,
            detail=f"missing at T3: {len(set(missing_t3))}",
        )

    return TierResult(
        taxon_id=taxon_id,
        tier=Tier.T3,
        required_params=required_t,
        missing_params=(),
        system_gaps=system_gaps_t,
        detail="all required approved; safety-critical double-reviewed",
    )


def derive_all_tiers(ks: KnowledgeSet, dictionary: Dictionary) -> dict[str, TierResult]:
    return {t.taxon_id: derive_tier(ks, t.taxon_id, dictionary) for t in ks.taxa()}
