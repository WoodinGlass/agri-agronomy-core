"""Suitability scoring: single-site and batch (M15, ADR-016).

Refuses rather than guesses:

- A critical hazard on the taxon short-circuits to ``ReferToAuthority``
  before any factor is classified (ADR-016 D-M15-S3).
- A missing site value returns ``InsufficientInput`` listing every
  missing field (Q2).
- A missing or non-applicable fact is propagated from ``resolve_facts``
  as-is (``Unknown`` / ``NotApplicable`` / ``InsufficientInput``) (Q3).
- A parameter whose fact is not a trapezoid yields ``not_applicable``.

Factor classification uses ``evaluate_trapezoid`` (formerly
``thresholds._evaluate``) so suitability and ``threshold_check`` share
exactly one trapezoid classifier.

The aggregation is rule-based (D-M15-S5): any critical -> unsuitable,
any suboptimal -> marginal, all optimal -> suitable. When every
``suitability_weight_<param>`` fact resolves to a scalar, the weighted
score is reported as a ``Notice(code="suitability_score")`` but does
**not** change the category (D-M15-S6).
"""

from __future__ import annotations

from typing import Any

from agri_core import RESOLUTION_POLICY_VERSION
from agri_core.models import (
    EvidenceGrade,
    FactStatus,
    InsufficientInput,
    Notice,
    Outcome,
    Provenance,
    ReferToAuthority,
    Subject,
    compute_request_id,
    not_applicable,
    ok_category,
)
from agri_core.models.fact import ScalarValue, TrapezoidValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_facts
from agri_core.suitability.models import Site
from agri_core.thresholds import evaluate_trapezoid

__all__ = ["batch_suitability", "site_suitability"]

_CALC_VERSION = "0.1.0"
_METHOD = "suitability_v1"

_SITE_PARAMS: tuple[str, ...] = (
    "soil_ph",
    "soil_ec",
    "air_temp_day",
    "air_temp_night",
    "air_rh",
    "vpd",
    "dli",
)

_LABELS: dict[str, str] = {
    "suitable": "Suitable",
    "marginal": "Marginal",
    "unsuitable": "Unsuitable",
}

_STATE_SCORES: dict[str, float] = {
    "optimal": 1.0,
    "suboptimal": 0.5,
    "critical": 0.0,
}


def site_suitability(
    pack: KnowledgeSet,
    taxon_id: str,
    site: Site,
    *,
    phase: str | None = None,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Classify a site as suitable, marginal or unsuitable for a taxon.

    Parameters
    ----------
    pack
        Loaded knowledge pack. No filesystem or clock access.
    taxon_id
        Opaque taxon identifier.
    site
        A ``Site`` with one value per site-facing parameter. A ``None``
        value makes the call refuse with ``InsufficientInput``.
    phase
        Biological phase used when a site-facing parameter carries one
        (``air_temp_day``, ``air_temp_night``, ``air_rh``, ``vpd``,
        ``dli``). If any such parameter is phase-bearing in the
        dictionary and ``phase`` is ``None``, the underlying
        ``resolve_facts`` returns ``InsufficientInput(missing=["phase"])``
        which is propagated unchanged.
    scope
        Scope for fact resolution (country, system, variety, ...).
    min_status
        Effective status floor. Defaults to ``"approved"``.
    """
    subject = Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation="site_suitability",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={"site": site.model_dump(), "phase": phase},
        pack_hash=pack.pack_hash,
    )

    # 1. Hazard short-circuit (D-M15-S3).
    try:
        hazards = pack.hazards_for(taxon_id)
    except KeyError:
        hazards = ()

    critical = [h for h in hazards if h.severity == "critical"]
    if critical:
        return ReferToAuthority(
            status="refer_to_authority",
            reason=("taxon has critical hazard(s): " + ", ".join(h.hazard_code for h in critical)),
            flags=sorted(h.hazard_code.upper() for h in critical),
            subject=subject,
            request_id=request_id,
        )

    hazard_notices = [
        Notice(
            code=f"hazard_{h.hazard_code}",
            message=f"{h.severity}: {h.reason} (authority: {h.authority})",
        )
        for h in hazards
    ]

    # 2. Site completeness (Q2).
    missing_site = [p for p in _SITE_PARAMS if getattr(site, p) is None]
    if missing_site:
        return InsufficientInput(
            status="insufficient_input",
            missing=missing_site,
            subject=subject,
            request_id=request_id,
        )

    # 3. Resolve all site facts + all weight facts in one call.
    weight_params = tuple(f"suitability_weight_{p}" for p in _SITE_PARAMS)
    resolved_all = resolve_facts(
        pack,
        taxon_id,
        list(_SITE_PARAMS) + list(weight_params),
        phase=phase,
        scope=scope,
        min_status=min_status,
    )

    # 4. Classify each site factor; propagate refusals as-is.
    factor_notices: list[Notice] = []
    evidence_grades: list[EvidenceGrade] = []
    fact_ids: list[str] = []
    source_ids: set[str] = set()
    category_states: dict[str, str] = {}

    for param in _SITE_PARAMS:
        fr = resolved_all[param]
        if not isinstance(fr, FactResolved):
            return fr
        if not isinstance(fr.value, TrapezoidValue):
            return not_applicable(
                reason=(
                    f"parameter {param!r} has shape {fr.value.shape!r}, "
                    "not trapezoid; site_suitability only classifies trapezoid facts"
                ),
                subject=subject,
                request_id=request_id,
            )
        value = getattr(site, param)
        assert value is not None
        state = evaluate_trapezoid(value, fr.value.pts)
        category_states[param] = state
        factor_notices.append(
            Notice(
                code=f"factor_{param}_{state}",
                message=f"{param}: {state} (value={value})",
            )
        )
        evidence_grades.append(fr.fact.evidence)
        fact_ids.append(fr.fact.fact_id)
        source_ids.update(fr.fact.src or ())

    # 5. Aggregation (D-M15-S5).
    if "critical" in category_states.values():
        category = "unsuitable"
    elif "suboptimal" in category_states.values():
        category = "marginal"
    else:
        category = "suitable"

    # 6. Weighted score (D-M15-S6): reported only, never consulted.
    all_weights_resolved = True
    for w in weight_params:
        w_fr = resolved_all[w]
        if not isinstance(w_fr, FactResolved) or not isinstance(w_fr.value, ScalarValue):
            all_weights_resolved = False
            break
    if all_weights_resolved:
        total_w = 0.0
        total_ws = 0.0
        for param in _SITE_PARAMS:
            w_fr = resolved_all[f"suitability_weight_{param}"]
            assert isinstance(w_fr, FactResolved)
            assert isinstance(w_fr.value, ScalarValue)
            wi = float(w_fr.value.value)
            total_w += wi
            total_ws += wi * _STATE_SCORES[category_states[param]]
        if total_w > 0.0:
            score = total_ws / total_w
            factor_notices.append(
                Notice(
                    code="suitability_score",
                    message=(
                        f"weighted score = {score:.3f} "
                        f"(reported for transparency; category is rule-based)"
                    ),
                )
            )

    # 7. Envelope + return.
    provenance = Provenance(
        fact_ids=sorted(fact_ids),
        pack_version=pack.manifest.version,
        pack_hash=pack.pack_hash,
        source_ids=sorted(source_ids),
        resolution_policy_version=RESOLUTION_POLICY_VERSION,
    )

    return ok_category(
        category=category,
        label=_LABELS[category],
        method=_METHOD,
        provenance=provenance,
        evidence=sorted(set(evidence_grades)),
        assumptions=[],
        warnings=hazard_notices + factor_notices,
        subject=subject,
        request_id=request_id,
    )


def batch_suitability(
    pack: KnowledgeSet,
    site: Site,
    taxon_ids: list[str],
    *,
    phase: str | None = None,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> list[Outcome]:
    """Evaluate the same site for several taxa.

    Semantically identical to calling :func:`site_suitability` once per
    taxon; results are in input order. No taxon lookup is shared across
    calls because each call needs its own ``Subject``/``request_id``.
    """
    return [
        site_suitability(pack, tid, site, phase=phase, scope=scope, min_status=min_status)
        for tid in taxon_ids
    ]
