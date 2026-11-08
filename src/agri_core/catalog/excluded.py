"""Excluded parameter IDs and matching helpers.

The shipped ``EXCLUDED_PARAM_IDS`` set is generated from the catalog by
``scripts/gen_climate_catalog_doc.py``. It is not edited by hand.
"""

from __future__ import annotations

from agri_core.catalog._excluded_generated import EXCLUDED_PARAM_IDS

__all__ = ["EXCLUDED_PARAM_IDS", "is_excluded", "matches_excluded"]


def is_excluded(param_id: str) -> bool:
    """True if ``param_id`` is a shipped excluded parameter."""
    return param_id in EXCLUDED_PARAM_IDS


def matches_excluded(
    param_id: str,
    *,
    prefix_match: bool = False,
) -> bool:
    """True if ``param_id`` matches an excluded row.

    With ``prefix_match=True``, an extension parameter that starts with
    an excluded ``param_id`` also matches (e.g. ``exclude_uv_c_dosing_dose``
    starts with ``exclude_uv_c_dosing``). This is off by default so that
    only exact matches are rejected.
    """
    if param_id in EXCLUDED_PARAM_IDS:
        return True
    if not prefix_match:
        return False
    return any(param_id.startswith(ex) for ex in EXCLUDED_PARAM_IDS)
