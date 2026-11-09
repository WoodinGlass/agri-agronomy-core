"""Irrigation modes: field_etc, paddy_awd, container_band.

All three modes read their crop-specific parameters from the pack via
``resolve_fact``; none of them invent a value. Missing data yields
``unknown``, a parameter that does not apply yields ``not_applicable``,
and a missing input yields ``insufficient_input``.

- ``irrigate_field_etc`` returns a numeric net irrigation depth
  (mm/day) for an open-field crop whose Kc is read from the pack.
- ``irrigate_paddy_awd`` returns a categorical action for alternate
  wetting and drying: ``reflood`` or ``hold``. When the current
  biological phase is listed in ``must_flood_phases`` the field is
  re-flooded regardless of the measured depth.
- ``irrigate_container_band`` returns a categorical action for
  container crops whose ``moisture_band`` (trapezoid) comes from the
  pack: ``irrigate``, ``hold`` or ``drain``.
"""

from __future__ import annotations

from typing import Any

from agri_core.models import (
    FactStatus,
    Notice,
    Outcome,
    Subject,
    compute_request_id,
    not_applicable,
    ok,
    ok_category,
)
from agri_core.models.fact import (
    EnumSetValue,
    ScalarValue,
    TrapezoidValue,
)
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_fact

__all__ = [
    "irrigate_container_band",
    "irrigate_field_etc",
    "irrigate_paddy_awd",
]

_CALC_VERSION = "0.1.0"


def _subject(taxon_id: str, calculation: str, scope: dict[str, Any] | None) -> Subject:
    return Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation=calculation,
        calculation_version=_CALC_VERSION,
    )


def _scalar(fr: FactResolved) -> float | None:
    if isinstance(fr.value, ScalarValue):
        return float(fr.value.value)
    return None


def _trapezoid(fr: FactResolved) -> tuple[float, float, float, float] | None:
    if isinstance(fr.value, TrapezoidValue):
        return fr.value.pts
    return None


def _enum_set(fr: FactResolved) -> list[str] | None:
    if isinstance(fr.value, EnumSetValue):
        return list(fr.value.values)
    return None


def _propagate_refusal(outcome: Outcome) -> Outcome:
    return outcome


def irrigate_field_etc(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    phase: str,
    et0_mm_day: float,
    effective_precip_mm_day: float = 0.0,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Net irrigation depth for an open-field crop (mm/day).

    ``ETc = Kc * ET0``; ``net = max(0, ETc - effective_precip)``.
    Kc comes from the pack (``phase_set = kc``). The caller supplies
    ET0 (for example from ``agri_core.climate.et0``) and the effective
    precipitation (0.0 by default; an assumption is emitted when it is
    the default).
    """
    subject = _subject(taxon_id, "irrigate_field_etc", scope)
    inputs = {
        "phase": phase,
        "et0_mm_day": et0_mm_day,
        "effective_precip_mm_day": effective_precip_mm_day,
    }
    request_id = compute_request_id(subject=subject, inputs=inputs, pack_hash=pack.pack_hash)

    if et0_mm_day < 0.0:
        raise ValueError(f"et0_mm_day must be >= 0, got {et0_mm_day}")
    if effective_precip_mm_day < 0.0:
        raise ValueError(f"effective_precip_mm_day must be >= 0, got {effective_precip_mm_day}")

    kc_fr = resolve_fact(
        pack,
        taxon_id,
        "kc",
        phase=phase,
        scope=scope,
        min_status=min_status,
    )
    if not isinstance(kc_fr, FactResolved):
        return _propagate_refusal(kc_fr)
    kc = _scalar(kc_fr)
    if kc is None:
        return not_applicable(
            reason="kc fact is not a scalar",
            subject=subject,
            request_id=request_id,
        )

    assumptions: list[Notice] = []
    if effective_precip_mm_day == 0.0:
        assumptions.append(
            Notice(
                code="no_effective_precip_assumed_0",
                message=(
                    "effective precipitation assumed 0 mm/day; "
                    "pass effective_precip_mm_day to override"
                ),
            )
        )

    etc = kc * et0_mm_day
    net = max(0.0, etc - effective_precip_mm_day)

    return ok(
        value=net,
        unit="millimeter/day",
        method="allen_1996_kc_curve",
        provenance=kc_fr.provenance,
        evidence=[kc_fr.fact.evidence],
        assumptions=assumptions,
        warnings=kc_fr.warnings,
        subject=subject,
        request_id=request_id,
    )


def irrigate_paddy_awd(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    phase: str,
    water_table_depth_cm: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Categorical AWD action: ``reflood`` or ``hold``.

    If ``phase`` is listed in ``must_flood_phases``, the field must be
    re-flooded regardless of the measured depth. Otherwise, ``reflood``
    when ``water_table_depth_cm >= awd_reflood_depth``; ``hold`` when
    the depth is shallower.

    ``water_table_depth_cm`` is measured positive downward from the
    soil surface (10.0 = 10 cm below the surface).
    """
    subject = _subject(taxon_id, "irrigate_paddy_awd", scope)
    inputs = {
        "phase": phase,
        "water_table_depth_cm": water_table_depth_cm,
    }
    request_id = compute_request_id(subject=subject, inputs=inputs, pack_hash=pack.pack_hash)

    if water_table_depth_cm < 0.0:
        # Negative means ponded above surface; treat as no deficit and hold.
        # Still requires must_flood check.
        pass

    fact_ids: list[str] = []
    evidence: list[str] = []

    # 1. Phase in must_flood_phases?
    flood_fr = resolve_fact(
        pack,
        taxon_id,
        "must_flood_phases",
        scope=scope,
        min_status=min_status,
    )
    if isinstance(flood_fr, FactResolved):
        phases = _enum_set(flood_fr)
        if phases and phase in phases:
            fact_ids.append(flood_fr.fact.fact_id)
            evidence.append(flood_fr.fact.evidence)
            from agri_core.models import Provenance

            return ok_category(
                category="reflood",
                label="Reflood",
                method="paddy_awd",
                provenance=Provenance(
                    fact_ids=fact_ids,
                    pack_version=pack.manifest.version,
                    pack_hash=pack.pack_hash,
                    source_ids=[],
                ),
                evidence=evidence,  # type: ignore[arg-type]
                warnings=flood_fr.warnings,
                subject=subject,
                request_id=request_id,
            )

    # 2. Depth-based decision
    depth_fr = resolve_fact(
        pack,
        taxon_id,
        "awd_reflood_depth",
        scope=scope,
        min_status=min_status,
    )
    if not isinstance(depth_fr, FactResolved):
        return _propagate_refusal(depth_fr)
    threshold = _scalar(depth_fr)
    if threshold is None:
        return not_applicable(
            reason="awd_reflood_depth is not a scalar",
            subject=subject,
            request_id=request_id,
        )

    fact_ids.append(depth_fr.fact.fact_id)
    evidence.append(depth_fr.fact.evidence)
    warnings = list(depth_fr.warnings)

    if water_table_depth_cm >= threshold:
        category, label = "reflood", "Reflood"
    else:
        category, label = "hold", "Hold"

    from agri_core.models import Provenance

    return ok_category(
        category=category,
        label=label,
        method="paddy_awd",
        provenance=Provenance(
            fact_ids=fact_ids,
            pack_version=pack.manifest.version,
            pack_hash=pack.pack_hash,
            source_ids=[],
        ),
        evidence=evidence,  # type: ignore[arg-type]
        warnings=warnings,
        subject=subject,
        request_id=request_id,
    )


def irrigate_container_band(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    current_moisture_pct: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Categorical container action: ``irrigate``, ``hold`` or ``drain``.

    The ``moisture_band`` trapezoid ``(abs_min, opt_min, opt_max,
    abs_max)`` comes from the pack. Below ``opt_min`` -> ``irrigate``;
    above ``opt_max`` -> ``drain``; inside the optimal band -> ``hold``.
    """
    subject = _subject(taxon_id, "irrigate_container_band", scope)
    inputs = {"current_moisture_pct": current_moisture_pct}
    request_id = compute_request_id(subject=subject, inputs=inputs, pack_hash=pack.pack_hash)

    if not (0.0 <= current_moisture_pct <= 100.0):
        raise ValueError(f"current_moisture_pct must be in [0, 100], got {current_moisture_pct}")

    band_fr = resolve_fact(
        pack,
        taxon_id,
        "moisture_band",
        scope=scope,
        min_status=min_status,
    )
    if not isinstance(band_fr, FactResolved):
        return _propagate_refusal(band_fr)
    pts = _trapezoid(band_fr)
    if pts is None:
        return not_applicable(
            reason="moisture_band fact is not a trapezoid",
            subject=subject,
            request_id=request_id,
        )

    _abs_min, opt_min, opt_max, _abs_max = pts

    if current_moisture_pct < opt_min:
        category, label = "irrigate", "Irrigate"
    elif current_moisture_pct > opt_max:
        category, label = "drain", "Drain"
    else:
        category, label = "hold", "Hold"

    return ok_category(
        category=category,
        label=label,
        method="container_band",
        provenance=band_fr.provenance,
        evidence=[band_fr.fact.evidence],
        warnings=band_fr.warnings,
        subject=subject,
        request_id=request_id,
    )
