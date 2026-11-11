"""Threshold checks: four-point trapezoid classification.

Returns :class:`CategoricalResult` (ADR-006) with ``category`` in
``{"optimal", "suboptimal", "critical"}``. Trapezoid values come from
the pack only; this module never invents a threshold.

Refusals from :func:`agri_core.registry.resolution.resolve_fact`
(``Unknown``, ``NotApplicable``, ``InsufficientInput``) are propagated
unchanged. A non-trapezoid fact returns ``not_applicable``.
"""

from __future__ import annotations

from typing import Any

from agri_core.models import (
    FactStatus,
    Outcome,
    Subject,
    compute_request_id,
    not_applicable,
    ok_category,
)
from agri_core.models.fact import TrapezoidValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_fact

__all__ = ["evaluate_trapezoid", "threshold_check"]

_CALC_VERSION = "0.1.0"

_LABELS: dict[str, str] = {
    "optimal": "Optimal",
    "suboptimal": "Suboptimal",
    "critical": "Critical",
}


def evaluate_trapezoid(value: float, pts: tuple[float, float, float, float]) -> str:
    """Classify ``value`` against ``pts = (abs_min, opt_min, opt_max, abs_max)``.

    Boundaries are inclusive on both ends (``value == abs_min`` and
    ``value == abs_max`` are suboptimal, not critical).
    """
    abs_min, opt_min, opt_max, abs_max = pts
    if opt_min <= value <= opt_max:
        return "optimal"
    if abs_min <= value <= abs_max:
        return "suboptimal"
    return "critical"


def threshold_check(
    pack: KnowledgeSet,
    taxon_id: str,
    parameter: str,
    *,
    value: float,
    phase: str | None = None,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Classify ``value`` against a trapezoid threshold fact for a taxon.

    The threshold trapezoid is read from the pack via ``resolve_fact``;
    the caller supplies only the raw value to classify. Refusals from
    resolution (missing fact, out-of-scope, non-matching taxon) are
    propagated as-is. A parameter whose fact is not a ``TrapezoidValue``
    yields ``not_applicable`` (the caller asked for a classification
    that only trapezoid facts support).

    Parameters
    ----------
    pack
        Loaded knowledge pack. No filesystem or clock access.
    taxon_id
        Opaque taxon identifier. Must exist in the pack.
    parameter
        Core or extension parameter. Must exist in the dictionary and
        apply to the taxon.
    value
        The raw value to classify, in the fact's unit.
    phase
        Required if the parameter carries a biological phase.
    scope
        Scope to resolve against (country, system, etc.). Defaults to
        empty, which matches any fact.
    min_status
        Effective status floor. Safety-critical parameters raise the
        floor to ``reviewed``; the elevation is reported in the
        propagated ``FactResolved.warnings``.
    """
    subject = Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation="threshold_check",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={"parameter": parameter, "value": value, "phase": phase},
        pack_hash=pack.pack_hash,
    )

    fr = resolve_fact(
        pack,
        taxon_id,
        parameter,
        phase=phase,
        scope=scope,
        min_status=min_status,
    )
    # FactResolved is a distinct model from Outcome's Result; only the
    # refusals (Unknown, NotApplicable, InsufficientInput) live in both.
    if not isinstance(fr, FactResolved):
        return fr

    if not isinstance(fr.value, TrapezoidValue):
        return not_applicable(
            reason=(
                f"parameter {parameter!r} has shape {fr.value.shape!r}, "
                "not trapezoid; threshold_check only classifies trapezoid facts"
            ),
            subject=subject,
            request_id=request_id,
        )

    category = evaluate_trapezoid(value, fr.value.pts)
    return ok_category(
        category=category,
        label=_LABELS[category],
        method="trapezoid_4pt",
        provenance=fr.provenance,
        evidence=[fr.fact.evidence],
        assumptions=[],
        warnings=fr.warnings,
        subject=subject,
        request_id=request_id,
    )
