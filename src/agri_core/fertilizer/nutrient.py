"""Fertilizer calculators: nutrient-to-product conversion with dose-cap enforcement.

The caller supplies the target nutrient amount (kg N, P2O5, or K2O per
hectare) and the product's guaranteed nutrient content (%). The engine
converts to product mass and enforces the per-application dose cap from
the pack.

Every cap is a safety-critical fact (``safety_class = dose_cap``). If the
cap is missing or below the safety floor, the calculation refuses; it
never falls back to a hardcoded number (K2).
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
)
from agri_core.models.fact import ScalarValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_fact
from agri_core.safety import apply_dose_cap

__all__ = [
    "fertilize_k2o",
    "fertilize_n",
    "fertilize_p2o5",
]

_CALC_VERSION = "0.1.0"
_METHOD = "product_composition_division"


def _subject(taxon_id: str, calculation: str, scope: dict[str, Any] | None) -> Subject:
    return Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation=calculation,
        calculation_version=_CALC_VERSION,
    )


def _fertilize(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    calculation: str,
    cap_key: str,
    nutrient_kg_ha: float,
    product_pct: float,
    pct_label: str,
    scope: dict[str, Any] | None,
    min_status: FactStatus | None,
) -> Outcome:
    if nutrient_kg_ha < 0.0:
        raise ValueError(f"nutrient_kg_ha must be >= 0, got {nutrient_kg_ha}")
    if not (0.0 < product_pct <= 100.0):
        raise ValueError(f"product_pct must be in (0, 100], got {product_pct}")

    subject = _subject(taxon_id, calculation, scope)
    inputs = {"nutrient_kg_ha": nutrient_kg_ha, "product_pct": product_pct}
    request_id = compute_request_id(subject=subject, inputs=inputs, pack_hash=pack.pack_hash)

    cap_fr = resolve_fact(pack, taxon_id, cap_key, scope=scope, min_status=min_status)
    if not isinstance(cap_fr, FactResolved):
        return cap_fr

    if not isinstance(cap_fr.value, ScalarValue):
        return not_applicable(
            reason=f"{cap_key} fact is not a scalar",
            subject=subject,
            request_id=request_id,
        )

    cap_value = float(cap_fr.value.value)
    effective_nutrient, capped = apply_dose_cap(requested=nutrient_kg_ha, cap=cap_value)
    product_kg = effective_nutrient / (product_pct / 100.0)

    warnings = list(cap_fr.warnings)
    if capped:
        warnings.append(
            Notice(
                code="dose_cap_applied",
                message=(
                    f"{pct_label} capped at {cap_value:g} kg/ha "
                    f"(requested {nutrient_kg_ha:g} kg/ha)"
                ),
            )
        )

    return ok(
        value=product_kg,
        unit="kilogram/hectare",
        method=_METHOD,
        provenance=cap_fr.provenance,
        evidence=[cap_fr.fact.evidence],
        assumptions=[],
        warnings=warnings,
        capped=capped,
        subject=subject,
        request_id=request_id,
    )


def fertilize_n(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    nutrient_kg_ha: float,
    product_n_pct: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = None,
) -> Outcome:
    """Convert a target nitrogen dose to product mass (kg/ha), with cap.

    ``product_kg_ha = effective_nutrient_kg_ha / (product_n_pct / 100)``.
    The effective nutrient is clamped to ``n_max_per_application`` from
    the pack. If that cap is missing or below the safety floor, the
    calculation refuses (K2). Never falls back to a hardcoded number.
    """
    return _fertilize(
        pack,
        taxon_id,
        calculation="fertilize_n",
        cap_key="n_max_per_application",
        nutrient_kg_ha=nutrient_kg_ha,
        product_pct=product_n_pct,
        pct_label="N",
        scope=scope,
        min_status=min_status,
    )


def fertilize_p2o5(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    nutrient_kg_ha: float,
    product_p2o5_pct: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = None,
) -> Outcome:
    """Convert a target P2O5 dose to product mass (kg/ha), with cap.

    ``nutrient_kg_ha`` is the target P2O5 amount. The effective value is
    clamped to ``p2o5_max_per_application`` from the pack. Refuses if
    that cap is missing or below the safety floor (K2).
    """
    return _fertilize(
        pack,
        taxon_id,
        calculation="fertilize_p2o5",
        cap_key="p2o5_max_per_application",
        nutrient_kg_ha=nutrient_kg_ha,
        product_pct=product_p2o5_pct,
        pct_label="P2O5",
        scope=scope,
        min_status=min_status,
    )


def fertilize_k2o(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    nutrient_kg_ha: float,
    product_k2o_pct: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = None,
) -> Outcome:
    """Convert a target K2O dose to product mass (kg/ha), with cap.

    ``nutrient_kg_ha`` is the target K2O amount. The effective value is
    clamped to ``k2o_max_per_application`` from the pack. Refuses if
    that cap is missing or below the safety floor (K2).
    """
    return _fertilize(
        pack,
        taxon_id,
        calculation="fertilize_k2o",
        cap_key="k2o_max_per_application",
        nutrient_kg_ha=nutrient_kg_ha,
        product_pct=product_k2o_pct,
        pct_label="K2O",
        scope=scope,
        min_status=min_status,
    )
