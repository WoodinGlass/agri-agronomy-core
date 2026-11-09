"""Stage resolution: annual age, annual thermal, or perennial events.

M13 part 2. Three modes, dispatched by arguments:

- **perennial events** (``events`` provided): the stage is the latest
  dated event at or before ``as_of_date``.
- **annual thermal** (``planting_date`` + ``gdd_cumulative`` provided):
  the phase cumulative thermal time (``phase_thermal_time`` facts) is
  accumulated until it reaches ``gdd_cumulative``.
- **annual age** (``planting_date`` only): the phase durations
  (``phase_duration`` facts) are accumulated until the elapsed days
  reach the number of days from ``planting_date`` to ``as_of_date``.

Phase names come from ``dictionary/vocab/phases_by_archetype.yaml``
(the taxon's archetype). Stage values come only from the pack: the
resolver reads ``phase_duration`` and ``phase_thermal_time`` via
``resolve_fact``; no duration is invented.

``ptu_cumulative`` is accepted but deferred: photothermal staging
requires a ``phase_photothermal_time`` parameter, which is not yet in
the dictionary. The function returns ``not_applicable`` with an
explanatory reason.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agri_core.models import (
    FactStatus,
    Outcome,
    Provenance,
    Subject,
    Unknown,
    compute_request_id,
    insufficient_input,
    not_applicable,
    ok_category,
)
from agri_core.models.fact import ScalarValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_fact

__all__ = ["resolve_stage"]

_CALC_VERSION = "0.1.0"


def _phases_source() -> Any:
    """Return a path-like source for phases_by_archetype.yaml."""
    try:
        from importlib.resources import files as _files

        pkg = _files("agri_core") / "_dictionary" / "vocab" / "phases_by_archetype.yaml"
        if pkg.is_file():
            return pkg
    except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError):
        pass
    return Path(__file__).resolve().parents[3] / "dictionary" / "vocab" / "phases_by_archetype.yaml"


@functools.lru_cache(maxsize=1)
def _load_phases_by_archetype() -> dict[str, list[str]]:
    source = _phases_source()
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw = data["phases_by_archetype"]
    out: dict[str, list[str]] = {}
    for arch, info in raw.items():
        out[arch] = list(info["phases"])
    return out


def _label_for(phase: str) -> str:
    return phase.replace("_", " ").title()


def _resolve_phase_fact(
    pack: KnowledgeSet,
    taxon_id: str,
    parameter: str,
    phase: str,
    min_status: FactStatus,
) -> float | None:
    """Return the scalar value of a phase fact, or None if absent/refused."""
    fr = resolve_fact(
        pack,
        taxon_id,
        parameter,
        phase=phase,
        min_status=min_status,
    )
    if not isinstance(fr, FactResolved):
        return None
    if not isinstance(fr.value, ScalarValue):
        return None
    return float(fr.value.value)


def _walk_phases_by_cumulative(
    pack: KnowledgeSet,
    taxon_id: str,
    phases: list[str],
    parameter: str,
    target: float,
    min_status: FactStatus,
) -> str | None:
    """Accumulate ``parameter`` across phases; return the phase where
    the running total still covers ``target``.

    Returns None if no phase fact was available at all.
    """
    cumulative = 0.0
    current: str | None = None
    for phase in phases:
        amount = _resolve_phase_fact(pack, taxon_id, parameter, phase, min_status)
        if amount is None:
            break
        cumulative += amount
        current = phase
        if cumulative >= target:
            break
    return current


def resolve_stage(
    pack: KnowledgeSet,
    taxon_id: str,
    as_of_date: date,
    *,
    planting_date: date | None = None,
    gdd_cumulative: float | None = None,
    ptu_cumulative: float | None = None,
    events: Mapping[str, date] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Resolve the biological phase of a taxon on ``as_of_date``.

    See the module docstring for the three modes.

    ``min_status`` applies to phase facts (``phase_duration`` and
    ``phase_thermal_time``). Defaults to ``"approved"``.
    """
    status = min_status or "approved"

    # ── Refusals that don't need the taxon ──
    if ptu_cumulative is not None:
        subject = Subject(
            taxon_id=taxon_id,
            scope={},
            calculation="resolve_stage",
            calculation_version=_CALC_VERSION,
        )
        request_id = compute_request_id(
            subject=subject,
            inputs={
                "as_of_date": as_of_date.isoformat(),
                "ptu_cumulative": ptu_cumulative,
            },
            pack_hash=pack.pack_hash,
        )
        return not_applicable(
            reason=(
                "photothermal staging requires a phase_photothermal_time "
                "parameter, which is not yet in the dictionary; deferred"
            ),
            subject=subject,
            request_id=request_id,
        )

    if events is not None and (planting_date is not None or gdd_cumulative is not None):
        subject = Subject(
            taxon_id=taxon_id,
            scope={},
            calculation="resolve_stage",
            calculation_version=_CALC_VERSION,
        )
        request_id = compute_request_id(
            subject=subject,
            inputs={"as_of_date": as_of_date.isoformat()},
            pack_hash=pack.pack_hash,
        )
        return insufficient_input(
            missing=["events_or_planting_date"],
            subject=subject,
            request_id=request_id,
        )

    if events is None and planting_date is None:
        subject = Subject(
            taxon_id=taxon_id,
            scope={},
            calculation="resolve_stage",
            calculation_version=_CALC_VERSION,
        )
        request_id = compute_request_id(
            subject=subject,
            inputs={"as_of_date": as_of_date.isoformat()},
            pack_hash=pack.pack_hash,
        )
        return insufficient_input(
            missing=["events_or_planting_date"],
            subject=subject,
            request_id=request_id,
        )

    # ── Resolve taxon ──
    try:
        taxon = pack.taxon(taxon_id)
    except KeyError:
        subject = Subject(
            taxon_id=taxon_id,
            scope={},
            calculation="resolve_stage",
            calculation_version=_CALC_VERSION,
        )
        request_id = compute_request_id(
            subject=subject,
            inputs={"as_of_date": as_of_date.isoformat()},
            pack_hash=pack.pack_hash,
        )
        return Unknown(
            status="unknown",
            reason=f"taxon {taxon_id!r} not in pack",
            code="no_match",
            subject=subject,
            request_id=request_id,
        )

    archetype = taxon.archetype
    phases_map = _load_phases_by_archetype()
    phases = phases_map.get(archetype)
    if not phases:
        subject = Subject(
            taxon_id=taxon_id,
            scope={},
            calculation="resolve_stage",
            calculation_version=_CALC_VERSION,
        )
        request_id = compute_request_id(
            subject=subject,
            inputs={"as_of_date": as_of_date.isoformat()},
            pack_hash=pack.pack_hash,
        )
        return insufficient_input(
            missing=[f"no_phase_vocabulary_for_archetype_{archetype}"],
            subject=subject,
            request_id=request_id,
        )

    subject = Subject(
        taxon_id=taxon_id,
        scope={},
        calculation="resolve_stage",
        calculation_version=_CALC_VERSION,
    )

    # ── Perennial: events ──
    if events is not None:
        request_id = compute_request_id(
            subject=subject,
            inputs={
                "as_of_date": as_of_date.isoformat(),
                "events": {k: v.isoformat() for k, v in events.items()},
            },
            pack_hash=pack.pack_hash,
        )
        # Filter to phases known for the archetype
        known = {p: d for p, d in events.items() if p in phases}
        if not known:
            return insufficient_input(
                missing=["no_events_match_archetype_phases"],
                subject=subject,
                request_id=request_id,
            )
        # Latest event <= as_of_date
        candidates = [(d, p) for p, d in known.items() if d <= as_of_date]
        if not candidates:
            return insufficient_input(
                missing=["no_phase_event_before_as_of_date"],
                subject=subject,
                request_id=request_id,
            )
        candidates.sort()
        _latest_date, event_stage = candidates[-1]
        return ok_category(
            category=event_stage,
            label=_label_for(event_stage),
            method="events",
            provenance=_make_provenance(pack, fact_ids=[]),
            evidence=[],
            assumptions=[],
            warnings=[],
            subject=subject,
            request_id=request_id,
        )

    # ── Annual: thermal (GDD) or age ──
    if planting_date is not None and planting_date > as_of_date:
        request_id = compute_request_id(
            subject=subject,
            inputs={
                "as_of_date": as_of_date.isoformat(),
                "planting_date": planting_date.isoformat(),
            },
            pack_hash=pack.pack_hash,
        )
        return insufficient_input(
            missing=["planting_date_after_as_of_date"],
            subject=subject,
            request_id=request_id,
        )

    if gdd_cumulative is not None:
        if gdd_cumulative < 0.0:
            request_id = compute_request_id(
                subject=subject,
                inputs={"as_of_date": as_of_date.isoformat(), "gdd_cumulative": gdd_cumulative},
                pack_hash=pack.pack_hash,
            )
            return insufficient_input(
                missing=["gdd_cumulative_negative"],
                subject=subject,
                request_id=request_id,
            )
        stage: str | None = _walk_phases_by_cumulative(
            pack, taxon_id, phases, "phase_thermal_time", gdd_cumulative, status
        )
        method = "thermal_time"
        request_id = compute_request_id(
            subject=subject,
            inputs={
                "as_of_date": as_of_date.isoformat(),
                "planting_date": planting_date.isoformat() if planting_date else None,
                "gdd_cumulative": gdd_cumulative,
            },
            pack_hash=pack.pack_hash,
        )
    else:
        # Age mode
        if planting_date is None:
            request_id = compute_request_id(
                subject=subject,
                inputs={"as_of_date": as_of_date.isoformat()},
                pack_hash=pack.pack_hash,
            )
            return insufficient_input(
                missing=["planting_date_or_gdd_cumulative"],
                subject=subject,
                request_id=request_id,
            )
        elapsed = float((as_of_date - planting_date).days)
        stage = _walk_phases_by_cumulative(
            pack, taxon_id, phases, "phase_duration", elapsed, status
        )
        method = "age"
        request_id = compute_request_id(
            subject=subject,
            inputs={
                "as_of_date": as_of_date.isoformat(),
                "planting_date": planting_date.isoformat(),
            },
            pack_hash=pack.pack_hash,
        )

    if stage is None:
        return insufficient_input(
            missing=["no_phase_facts"],
            subject=subject,
            request_id=request_id,
        )
    return ok_category(
        category=stage,
        label=_label_for(stage),
        method=method,
        provenance=_make_provenance(pack, fact_ids=[]),
        evidence=[],
        assumptions=[],
        warnings=[],
        subject=subject,
        request_id=request_id,
    )


def _make_provenance(pack: KnowledgeSet, *, fact_ids: list[str]) -> Provenance:
    return Provenance(
        fact_ids=fact_ids,
        pack_version=pack.manifest.version,
        pack_hash=pack.pack_hash,
        source_ids=[],
    )
