"""Water-quality indices and limits (M14).

- ``compute_sar``: Sodium Adsorption Ratio (Richards 1954). Pure math,
  no pack; returns the dimensionless index. Classification is up to the
  caller against a crop-specific threshold from the pack.
- ``compute_rsc``: Residual Sodium Carbonate (Eaton 1950). Pure math,
  no pack; returns the dimensionless index. Value may be negative.
- ``check_water_quality``: compare caller-supplied EC and temperature
  against limits from the pack (``water_ec_max``, ``water_temp_max``).
  Categorical: ``ok``, ``exceed_ec``, ``exceed_temp``, ``exceed_both``.

None of the three hardcodes a threshold; limits come only from the pack.
An unknown-valued limit fact is surfaced as ``Unknown`` (code=None, since
``value_unknown`` is not yet an active registry code).
"""

from __future__ import annotations

import math
from typing import Any

from agri_core.models import (
    EvidenceGrade,
    FactStatus,
    Notice,
    Outcome,
    Provenance,
    Result,
    Subject,
    Unknown,
    compute_request_id,
    not_applicable,
    ok,
    ok_category,
)
from agri_core.models.fact import ScalarValue, UnknownValue
from agri_core.pack.knowledge_set import KnowledgeSet
from agri_core.registry.resolution import FactResolved, resolve_fact

__all__ = [
    "check_water_quality",
    "compute_rsc",
    "compute_sar",
]

_CALC_VERSION = "0.1.0"

_LABELS = {
    "ok": "OK",
    "exceed_ec": "EC exceeds limit",
    "exceed_temp": "Temperature exceeds limit",
    "exceed_both": "EC and temperature exceed limits",
}


def _require_nonneg(name: str, value: float) -> None:
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0, got {value}")


def _empty_provenance() -> Provenance:
    return Provenance(
        fact_ids=[],
        pack_version=None,
        pack_hash=None,
        source_ids=[],
    )


def compute_sar(
    *,
    na_meq_l: float,
    ca_meq_l: float,
    mg_meq_l: float,
) -> Result:
    """Sodium Adsorption Ratio: ``Na / sqrt((Ca + Mg) / 2)``.

    Inputs are milliequivalents per litre. The result is a dimensionless
    index; the caller classifies it against a crop- or soil-specific
    threshold from the pack. Richards 1954 (USDA Handbook 60) equation
    only; no tables are reproduced.
    """
    _require_nonneg("na_meq_l", na_meq_l)
    _require_nonneg("ca_meq_l", ca_meq_l)
    _require_nonneg("mg_meq_l", mg_meq_l)
    denom = (ca_meq_l + mg_meq_l) / 2.0
    if denom <= 0.0:
        raise ValueError(f"(ca_meq_l + mg_meq_l) / 2 must be > 0, got {denom}")
    value = na_meq_l / math.sqrt(denom)

    subject = Subject(
        taxon_id=None,
        scope={},
        calculation="compute_sar",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "na_meq_l": na_meq_l,
            "ca_meq_l": ca_meq_l,
            "mg_meq_l": mg_meq_l,
        },
        pack_hash=None,
    )
    return ok(
        value=value,
        unit="dimensionless",
        method="richards_1954_sar",
        provenance=_empty_provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def compute_rsc(
    *,
    co3_meq_l: float,
    hco3_meq_l: float,
    ca_meq_l: float,
    mg_meq_l: float,
) -> Result:
    """Residual Sodium Carbonate: ``(CO3 + HCO3) - (Ca + Mg)``.

    Inputs are milliequivalents per litre. The value is a dimensionless
    index; it may be negative, which is a valid mathematical result and
    is not treated as an error. Eaton 1950 equation only; no tables are
    reproduced.
    """
    _require_nonneg("co3_meq_l", co3_meq_l)
    _require_nonneg("hco3_meq_l", hco3_meq_l)
    _require_nonneg("ca_meq_l", ca_meq_l)
    _require_nonneg("mg_meq_l", mg_meq_l)
    value = (co3_meq_l + hco3_meq_l) - (ca_meq_l + mg_meq_l)

    subject = Subject(
        taxon_id=None,
        scope={},
        calculation="compute_rsc",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={
            "co3_meq_l": co3_meq_l,
            "hco3_meq_l": hco3_meq_l,
            "ca_meq_l": ca_meq_l,
            "mg_meq_l": mg_meq_l,
        },
        pack_hash=None,
    )
    return ok(
        value=value,
        unit="dimensionless",
        method="eaton_1950_rsc",
        provenance=_empty_provenance(),
        evidence=[],
        subject=subject,
        request_id=request_id,
    )


def _resolve_limit(
    pack: KnowledgeSet,
    taxon_id: str,
    parameter: str,
    *,
    scope: dict[str, Any] | None,
    min_status: FactStatus | None,
    subject: Subject,
    request_id: str,
) -> tuple[float, str, EvidenceGrade, list[Notice]] | Outcome:
    """Resolve a scalar limit. On success return (value, fact_id, evidence, warnings).

    Any refusal (Unknown / NotApplicable / InsufficientInput) is returned
    as-is; an UnknownValue inside a FactResolved becomes Unknown(code=None).
    """
    fr = resolve_fact(pack, taxon_id, parameter, scope=scope, min_status=min_status)
    if not isinstance(fr, FactResolved):
        return fr
    if isinstance(fr.value, UnknownValue):
        return Unknown(
            status="unknown",
            reason=f"{parameter}: {fr.value.reason}",
            code=None,
            subject=subject,
            request_id=request_id,
        )
    if not isinstance(fr.value, ScalarValue):  # pragma: no cover
        return not_applicable(
            reason=f"{parameter} fact has unexpected shape {fr.value.shape}",
            subject=subject,
            request_id=request_id,
        )
    return (
        float(fr.value.value),
        fr.fact.fact_id,
        fr.fact.evidence,
        fr.warnings,
    )


def check_water_quality(
    pack: KnowledgeSet,
    taxon_id: str,
    *,
    ec_ds_m: float,
    temp_c: float,
    scope: dict[str, Any] | None = None,
    min_status: FactStatus | None = "approved",
) -> Outcome:
    """Check water EC and temperature against pack limits.

    Compares ``ec_ds_m`` with ``water_ec_max`` and ``temp_c`` with
    ``water_temp_max``. Limits come only from the pack. A limit whose
    fact value is marked unknown produces ``Unknown``; a missing limit
    propagates the underlying refusal.

    Returns ``CategoricalResult`` with ``category`` one of:

    - ``ok``: both values are at or below their limit
    - ``exceed_ec``: EC exceeds the limit, temperature does not
    - ``exceed_temp``: temperature exceeds the limit, EC does not
    - ``exceed_both``: both exceed
    """
    _require_nonneg("ec_ds_m", ec_ds_m)

    subject = Subject(
        taxon_id=taxon_id,
        scope=dict(scope or {}),
        calculation="check_water_quality",
        calculation_version=_CALC_VERSION,
    )
    request_id = compute_request_id(
        subject=subject,
        inputs={"ec_ds_m": ec_ds_m, "temp_c": temp_c},
        pack_hash=pack.pack_hash,
    )

    # Resolve temperature limit first: its sample-pack fact may be unknown.
    temp_r = _resolve_limit(
        pack,
        taxon_id,
        "water_temp_max",
        scope=scope,
        min_status=min_status,
        subject=subject,
        request_id=request_id,
    )
    if not isinstance(temp_r, tuple):
        return temp_r
    temp_max, temp_fid, temp_ev, temp_warnings = temp_r

    ec_r = _resolve_limit(
        pack,
        taxon_id,
        "water_ec_max",
        scope=scope,
        min_status=min_status,
        subject=subject,
        request_id=request_id,
    )
    if not isinstance(ec_r, tuple):
        return ec_r
    ec_max, ec_fid, ec_ev, ec_warnings = ec_r

    exceed_temp = temp_c > temp_max
    exceed_ec = ec_ds_m > ec_max

    if exceed_temp and exceed_ec:
        category = "exceed_both"
    elif exceed_temp:
        category = "exceed_temp"
    elif exceed_ec:
        category = "exceed_ec"
    else:
        category = "ok"

    return ok_category(
        category=category,
        label=_LABELS[category],
        method="water_quality_limits",
        provenance=Provenance(
            fact_ids=[temp_fid, ec_fid],
            pack_version=pack.manifest.version,
            pack_hash=pack.pack_hash,
            source_ids=[],
        ),
        evidence=[temp_ev, ec_ev],
        warnings=temp_warnings + ec_warnings,
        subject=subject,
        request_id=request_id,
    )
