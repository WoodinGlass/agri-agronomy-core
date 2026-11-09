"""apply_dose_cap: helper contract + 100% coverage target."""

from __future__ import annotations

import pytest

from agri_core.safety import apply_dose_cap

pytestmark = pytest.mark.unit


# ─── happy path ───


def test_below_cap_returns_requested() -> None:
    effective, capped = apply_dose_cap(requested=30.0, cap=80.0)
    assert effective == 30.0
    assert capped is False


def test_at_cap_returns_requested_not_capped() -> None:
    effective, capped = apply_dose_cap(requested=80.0, cap=80.0)
    assert effective == 80.0
    assert capped is False


def test_above_cap_returns_cap_capped() -> None:
    effective, capped = apply_dose_cap(requested=120.0, cap=80.0)
    assert effective == 80.0
    assert capped is True


def test_zero_requested_is_valid() -> None:
    effective, capped = apply_dose_cap(requested=0.0, cap=80.0)
    assert effective == 0.0
    assert capped is False


def test_just_above_cap() -> None:
    effective, capped = apply_dose_cap(requested=80.0001, cap=80.0)
    assert effective == 80.0
    assert capped is True


# ─── errors ───


def test_negative_requested_raises() -> None:
    with pytest.raises(ValueError, match="requested must be >= 0"):
        apply_dose_cap(requested=-1.0, cap=80.0)


def test_zero_cap_raises() -> None:
    with pytest.raises(ValueError, match="cap must be > 0"):
        apply_dose_cap(requested=10.0, cap=0.0)


def test_negative_cap_raises() -> None:
    with pytest.raises(ValueError, match="cap must be > 0"):
        apply_dose_cap(requested=10.0, cap=-5.0)
