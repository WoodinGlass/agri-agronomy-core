"""Propagation planner: dated propagation_plan() (M15, ADR-016).

P5 fills a PropagationPlan from a pack. The planner reads
``propagation_method``, ``propagation_duration_days`` and
``propagation_start_months`` via resolve_facts (P4a); everything else
comes from the caller (start_date, method) or from fixed step
durations in code.

Fixed-duration step names (`prepare`, `establish`, `ready`) are
recorded via ``Notice(code="propagation_step_durations_defaulted")``
in the plan's ``assumptions`` so callers know those values do not come
from the pack. See ADR-016 amendment at P10.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from agri_core import RESOLUTION_POLICY_VERSION
from agri_core.models import (
    EvidenceGrade,
    FactStatus,
    Notice,
    Provenance,
    Subject,
    compute_request_id,
    not_applicable,
)
from agri_core.models.fact import EnumSetValue, ScalarValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.propagation.models import (
    PropagationOutcome,
    PropagationPlan,
    PropagationStep,
    PropagationStepName,
)
from agri_core.registry.resolution import FactResolved, resolve_facts

__all__ = ["propagation_plan"]

_CALC_VERSION = "0.1.0"

_PROP_PARAMS: tuple[str, ...] = (
    "propagation_method",
    "propagation_duration_days",
    "propagation_start_months",
)

# Fixed durations for the three "wrapper" step names. The `propagate`
# step's duration is read from the pack (propagation_duration_days).
_STEP_DURATIONS_FIXED: dict[PropagationStepName, int] = {
    "prepare": 1,
    "establish": 7,
    "ready": 1,
}


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in *month* of *year* (leap-aware)."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _shift_to_valid_month(start: date, valid_months: tuple[int, ...]) -> tuple[date, bool]:
    """Return (actual_start, shifted) shifting forward to the first valid month.

    Day-of-month is preserved when possible; clamped to month-end when
    the target month is shorter.
    """
    if not valid_months or start.month in valid_months:
        return start, False
    for offset in range(1, 13):
        total = (start.month - 1) + offset
        target_month = (total % 12) + 1
        target_year = start.year + (total // 12)
        if target_month in valid_months:
            day = min(start.day, _days_in_month(target_year, target_month))
            return date(target_year, target_month, day), True
    return start, False


def _integral_days(value: float, *, tolerance: float = 1e-9) -> int | None:
    """Return value as an integer day count if integral and positive.

    Returns None if the value is not an integer within *tolerance* or
    is not positive.
    """
    if value <= 0:
        return None
    rounded = round(value)
    if abs(value - rounded) > tolerance:
        return None
    return int(rounded)


def propagation_plan(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    start_date: date,
    method: str,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> PropagationOutcome:
    """Build a dated propagation plan for a taxon and method.

    Reads ``propagation_method``, ``propagation_duration_days`` and
    ``propagation_start_months`` from the pack. ``method`` must be in the
    resolved method set or the call refuses with ``NotApplicable``.

    ``start_date`` is shifted to the first valid month if needed; the
    plan's ``start_date`` and ``steps[0].start_date`` record the actual
    start. Only ``propagate`` gets its duration from the pack; the other
    three step names use fixed durations (a ``Notice`` records this).
    """
    subject = Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation="propagation_plan",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={"start_date": start_date.isoformat(), "method": method},
        pack_hash=pack.pack_hash,
    )

    resolved = resolve_facts(
        pack,
        taxon_id,
        list(_PROP_PARAMS),
        scope=scope,
        min_status=min_status,
    )

    # 1. method
    method_fr = resolved["propagation_method"]
    if not isinstance(method_fr, FactResolved):
        return method_fr
    if not isinstance(method_fr.value, EnumSetValue):
        return not_applicable(
            reason="propagation_method is not an enum_set fact",
            subject=subject,
            request_id=request_id,
        )
    if method not in method_fr.value.values:
        return not_applicable(
            reason=(
                f"method {method!r} not recorded for taxon {taxon_id!r}; "
                f"available: {sorted(method_fr.value.values)}"
            ),
            subject=subject,
            request_id=request_id,
        )

    # 2. duration (mandatory)
    duration_fr = resolved["propagation_duration_days"]
    if not isinstance(duration_fr, FactResolved):
        return duration_fr
    if not isinstance(duration_fr.value, ScalarValue):
        return not_applicable(
            reason="propagation_duration_days is not a scalar fact",
            subject=subject,
            request_id=request_id,
        )
    raw_duration = float(duration_fr.value.value)
    propagate_days = _integral_days(raw_duration)
    if propagate_days is None:
        return not_applicable(
            reason=(
                f"propagation_duration_days={raw_duration} is not a positive integer number of days"
            ),
            subject=subject,
            request_id=request_id,
        )

    # 3. start_months (optional; default = any month)
    assumptions: list[Notice] = []
    start_months_fr = resolved["propagation_start_months"]
    extra_fact_ids: list[str] = []
    extra_source_ids: set[str] = set()
    if isinstance(start_months_fr, FactResolved) and isinstance(
        start_months_fr.value, EnumSetValue
    ):
        valid_months = tuple(sorted(int(m) for m in start_months_fr.value.values))
        extra_fact_ids.append(start_months_fr.fact.fact_id)
        extra_source_ids.update(start_months_fr.fact.src or ())
    else:
        valid_months = tuple(range(1, 13))
        assumptions.append(
            Notice(
                code="propagation_start_months_defaulted",
                message="propagation_start_months not resolved; using any month",
            )
        )

    # 4. shift if needed
    actual_start, shifted = _shift_to_valid_month(start_date, valid_months)
    warnings: list[Notice] = []
    if shifted:
        warnings.append(
            Notice(
                code="propagation_start_shifted",
                message=(
                    f"start_date shifted from {start_date.isoformat()} to "
                    f"{actual_start.isoformat()} (valid months: "
                    f"{sorted(valid_months)})"
                ),
            )
        )

    # 5. build 4 contiguous steps: prepare(1) -> propagate(N) -> establish(7) -> ready(1)
    durations: list[tuple[PropagationStepName, int]] = [
        ("prepare", _STEP_DURATIONS_FIXED["prepare"]),
        ("propagate", propagate_days),
        ("establish", _STEP_DURATIONS_FIXED["establish"]),
        ("ready", _STEP_DURATIONS_FIXED["ready"]),
    ]
    steps: list[PropagationStep] = []
    cursor = actual_start
    for name, days in durations:
        end = cursor + timedelta(days=days - 1)
        steps.append(
            PropagationStep(
                step_name=name,
                start_date=cursor,
                end_date=end,
                duration_days=days,
            )
        )
        cursor = end + timedelta(days=1)

    assumptions.append(
        Notice(
            code="propagation_step_durations_defaulted",
            message=(
                "prepare=1d, establish=7d, ready=1d are fixed defaults; "
                "only 'propagate' duration comes from the pack"
            ),
        )
    )

    # 6. envelope
    fact_ids = [
        method_fr.fact.fact_id,
        duration_fr.fact.fact_id,
        *extra_fact_ids,
    ]
    source_ids = set(method_fr.fact.src or ()) | set(duration_fr.fact.src or ()) | extra_source_ids
    evidence: list[EvidenceGrade] = sorted(
        {
            method_fr.fact.evidence,
            duration_fr.fact.evidence,
        }
    )
    provenance = Provenance(
        fact_ids=sorted(fact_ids),
        pack_version=pack.manifest.version,
        pack_hash=pack.pack_hash,
        source_ids=sorted(source_ids),
        resolution_policy_version=RESOLUTION_POLICY_VERSION,
    )

    return PropagationPlan(
        status="ok",
        taxon_id=taxon_id,
        method=method,
        start_date=actual_start,
        steps=steps,
        subject=subject,
        request_id=request_id,
        provenance=provenance,
        evidence=evidence,
        assumptions=assumptions,
        warnings=warnings,
    )
