"""Contants parity for the diff core (HP#6).

ADR-019 Phase E: the field-set constants are the Python source of
truth. `_diff_config_args()` is the *only* way native adapters receive
them; Rust never stores a copy. Any drift here means a native adapter
would silently disagree with the Python oracle about which fields
trigger a violation.

Three invariants, all pure Python (no native extension needed):

1. Each constant is an immutable frozenset.
2. The acceptable and violation fields are disjoint; no field may
   be both a "safe edit" and a "frozen content" field at once.
3. `_diff_config_args()` returns exactly the three constants in the
   declared order (acceptable, violation, protected-statuses).
"""

from __future__ import annotations

import pytest

from agri_core.pack.diff import (
    _ACCEPTABLE_FIELDS,
    _REVIEWED_STATUSES,
    _VIOLATION_FIELDS,
    _diff_config_args,
)

pytestmark = pytest.mark.contract


def test_acceptable_fields_is_frozenset() -> None:
    assert isinstance(_ACCEPTABLE_FIELDS, frozenset)


def test_acceptable_and_violation_disjoint() -> None:
    assert _ACCEPTABLE_FIELDS.isdisjoint(_VIOLATION_FIELDS)


def test_reviewed_statuses_exact() -> None:
    assert frozenset({"reviewed", "approved"}) == _REVIEWED_STATUSES


def test_diff_config_args_matches_constants() -> None:
    acceptable, violation, protected = _diff_config_args()
    assert acceptable is _ACCEPTABLE_FIELDS
    assert violation is _VIOLATION_FIELDS
    assert protected is _REVIEWED_STATUSES
