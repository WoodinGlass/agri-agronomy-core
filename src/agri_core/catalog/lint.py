"""Lint a loaded climate parameter catalog.

Every check returns a ``Finding``. Errors block; warnings do not.
Unit parsing is delegated to pint; custom units (``pH``, ``ppm``,
``percent``, ``degree_day``) are accepted via ``CANONICAL_UNITS``.
"""

from __future__ import annotations

import functools
from datetime import date as _date
from typing import TYPE_CHECKING, Any

import pint

from agri_core.catalog.models import (
    CatalogKind,
    CatalogSafetyTier,
    CatalogStatus,
    CommercialUse,
)
from agri_core.models.finding import Finding, FindingLocation, FindingSeverity
from agri_core.models.units import CANONICAL_UNITS

if TYPE_CHECKING:
    from agri_core.catalog.models import CatalogRow

__all__ = ["lint_catalog"]

_STALE_DAYS: int = 365


@functools.lru_cache(maxsize=1)
def _registry() -> Any:
    return pint.UnitRegistry()


def _unit_ok(unit: str) -> bool:
    """True if ``unit`` is a canonical unit or parses via pint."""
    if unit in CANONICAL_UNITS:
        return True
    try:
        _registry().Unit(unit)
    except (pint.errors.PintError, ValueError, TypeError):
        return False
    return True


def _finding(
    code: str,
    message: str,
    param_id: str,
    *,
    severity: FindingSeverity = FindingSeverity.ERROR,
) -> Finding:
    return Finding(
        code=code,
        severity=severity,
        message=message,
        location=FindingLocation(key=param_id),
    )


def lint_catalog(
    rows: list[CatalogRow],
    *,
    dictionary_keys: set[str] | None = None,
    reference_date: _date | None = None,
) -> list[Finding]:
    """Lint catalog rows; returns findings (empty = clean).

    The ``dictionary_keys`` parameter, when provided, enables the
    ``pack_value`` cross-check: every ``pack_value.param_id`` must be a
    key in the core dictionary.
    """
    findings: list[Finding] = []
    today = reference_date or _date.today()

    for row in rows:
        # 1. commercial_use
        if row.kind != CatalogKind.EXCLUDED and row.commercial_use != CommercialUse.YES:
            findings.append(
                _finding(
                    "CATALOG_COMMERCIAL_USE",
                    f"param {row.param_id!r} is {row.kind.value} but "
                    f"commercial_use={row.commercial_use.value!r} "
                    f"(must be 'yes')",
                    row.param_id,
                )
            )

        # 2. safety_tier high must be excluded
        if row.safety_tier == CatalogSafetyTier.HIGH and row.kind != CatalogKind.EXCLUDED:
            findings.append(
                _finding(
                    "CATALOG_HIGH_SAFETY_NOT_EXCLUDED",
                    f"param {row.param_id!r} has safety_tier='high' but "
                    f"kind={row.kind.value!r} (must be 'excluded')",
                    row.param_id,
                )
            )

        # 3. computed + implemented: method_ref and test_id required
        if row.kind == CatalogKind.COMPUTED and row.status == CatalogStatus.IMPLEMENTED:
            if not row.method_ref or row.method_ref.strip().upper() == "TBD":
                findings.append(
                    _finding(
                        "CATALOG_COMPUTED_NO_METHOD",
                        f"param {row.param_id!r} is computed+implemented but "
                        f"method_ref is empty or 'TBD'",
                        row.param_id,
                    )
                )
            if not row.test_id or row.test_id.strip().upper() == "TBD":
                findings.append(
                    _finding(
                        "CATALOG_COMPUTED_NO_TEST",
                        f"param {row.param_id!r} is computed+implemented but "
                        f"test_id is empty or 'TBD'",
                        row.param_id,
                    )
                )

        # 4. excluded / backlog: reason required
        if row.status in (CatalogStatus.EXCLUDED, CatalogStatus.BACKLOG) and not row.reason:
            findings.append(
                _finding(
                    "CATALOG_MISSING_REASON",
                    f"param {row.param_id!r} status={row.status.value} requires a reason",
                    row.param_id,
                )
            )

        # 5. unit must be pint-parseable or canonical (if non-empty)
        if row.unit and not _unit_ok(row.unit):
            findings.append(
                _finding(
                    "CATALOG_UNIT_UNPARSEABLE",
                    f"param {row.param_id!r} unit {row.unit!r} not parseable "
                    f"by pint and not in CANONICAL_UNITS",
                    row.param_id,
                )
            )

        # 6. pack_value: param_id must exist in dictionary (when provided)
        if (
            row.kind == CatalogKind.PACK_VALUE
            and dictionary_keys is not None
            and row.param_id not in dictionary_keys
        ):
            findings.append(
                _finding(
                    "CATALOG_PACK_VALUE_NOT_IN_DICTIONARY",
                    f"param {row.param_id!r} kind=pack_value but not a dictionary key",
                    row.param_id,
                )
            )

        # 7. checked_on freshness (WARNING only)
        try:
            check = _date.fromisoformat(row.checked_on)
        except ValueError:
            continue  # model validator catches; do not duplicate
        age = (today - check).days
        if age > _STALE_DAYS:
            findings.append(
                _finding(
                    "CATALOG_STALE_LICENSE_CHECK",
                    f"param {row.param_id!r} checked_on={row.checked_on} "
                    f"is {age} days old (>{_STALE_DAYS})",
                    row.param_id,
                    severity=FindingSeverity.WARNING,
                )
            )

    return findings
