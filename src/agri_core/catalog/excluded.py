"""Excluded parameter IDs and matching helpers.

The shipped ``EXCLUDED_PARAM_IDS`` set is generated from the catalog by
``scripts/gen_climate_catalog_doc.py``. It is not edited by hand.
"""

from __future__ import annotations

import functools

from agri_core.catalog._excluded_generated import EXCLUDED_PARAM_IDS

__all__ = ["EXCLUDED_PARAM_IDS", "is_excluded", "matches_excluded"]

_EXCLUDE_PREFIX = "exclude_"


@functools.lru_cache(maxsize=1)
def _stripped_subjects() -> frozenset[str]:
    """Excluded param_ids with the ``exclude_`` prefix stripped.

    ``exclude_uv_c_dosing`` becomes ``uv_c_dosing``. The set is used as
    the prefix subject, so an extension parameter such as
    ``uv_c_dosing_estimated`` is caught by the excluded UV-C row.
    """
    return frozenset(
        pid[len(_EXCLUDE_PREFIX) :] for pid in EXCLUDED_PARAM_IDS if pid.startswith(_EXCLUDE_PREFIX)
    )


def is_excluded(param_id: str) -> bool:
    """True if ``param_id`` is a shipped excluded parameter."""
    return param_id in EXCLUDED_PARAM_IDS


def matches_excluded(
    param_id: str,
    *,
    prefix_match: bool = False,
) -> bool:
    """True if ``param_id`` matches an excluded row.

    With ``prefix_match=True``, the ``exclude_`` prefix is stripped from
    each shipped id and the remaining subject is used as a prefix. An
    extension parameter such as ``uv_c_dosing_estimated`` or
    ``pesticide_dose_adjusted`` matches; ``gdd_base`` and
    ``dosing_interval`` do not. This is off by default so that only
    exact matches are rejected.
    """
    if param_id in EXCLUDED_PARAM_IDS:
        return True
    if not prefix_match:
        return False
    subjects = _stripped_subjects()
    if param_id in subjects:
        return True
    return any(param_id.startswith(s + "_") for s in subjects)
