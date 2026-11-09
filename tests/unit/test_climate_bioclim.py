"""Bioclimatic variables: bio_01, bio_06, bio_07, bio_12-bio_15."""

from __future__ import annotations

import pytest

from agri_core.climate import (
    bio_01,
    bio_06,
    bio_07,
    bio_12,
    bio_13,
    bio_14,
    bio_15,
)
from agri_core.models import NotApplicable, Result, is_success

pytestmark = pytest.mark.unit

_TEMP = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0]
_PRECIP_FLAT = [100.0] * 12
_PRECIP_VAR = [50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 300.0, 250.0, 200.0, 150.0, 100.0]


def _v(o: object) -> float:
    assert isinstance(o, Result), f"not Result: {o!r}"
    return o.value


# ─── bio_01 ───


def test_bio_01_mean() -> None:
    out = bio_01(monthly_temp_c=_TEMP)
    assert _v(out) == pytest.approx(15.5, abs=1e-9)
    assert out.unit == "degree_Celsius"
    assert out.method == "nix_1986"


# ─── bio_06 ───


def test_bio_06_min() -> None:
    out = bio_06(monthly_temp_c=_TEMP)
    assert _v(out) == 10.0


# ─── bio_07 ───


def test_bio_07_range() -> None:
    out = bio_07(monthly_temp_c=_TEMP)
    assert _v(out) == 11.0  # 21 - 10


# ─── bio_12 ───


def test_bio_12_sum_flat() -> None:
    out = bio_12(monthly_precip_mm=_PRECIP_FLAT)
    assert _v(out) == 1200.0
    assert out.unit == "millimeter"


def test_bio_12_sum_var() -> None:
    out = bio_12(monthly_precip_mm=_PRECIP_VAR)
    # sum = 2400
    assert _v(out) == 2400.0


# ─── bio_13 / bio_14 ───


def test_bio_13_max() -> None:
    out = bio_13(monthly_precip_mm=_PRECIP_VAR)
    assert _v(out) == 350.0


def test_bio_14_min() -> None:
    out = bio_14(monthly_precip_mm=_PRECIP_VAR)
    assert _v(out) == 50.0


# ─── bio_15 ───


def test_bio_15_flat_zero_cv() -> None:
    out = bio_15(monthly_precip_mm=_PRECIP_FLAT)
    assert _v(out) == pytest.approx(0.0, abs=1e-9)
    assert out.unit == "percent"


def test_bio_15_sparse_cv() -> None:
    # [0,0,...,0,12]: mean=1, sample stdev = sqrt(12) ≈ 3.4641,
    # CV = 100 * 3.4641 / 1 = 346.41
    series = [0.0] * 11 + [12.0]
    out = bio_15(monthly_precip_mm=series)
    assert _v(out) == pytest.approx(346.41, abs=0.5)


def test_bio_15_zero_mean_not_applicable() -> None:
    out = bio_15(monthly_precip_mm=[0.0] * 12)
    assert isinstance(out, NotApplicable)
    assert out.status == "not_applicable"


# ─── length validation ───


@pytest.mark.parametrize("n", [0, 1, 11, 13])
def test_length_must_be_12_temp(n: int) -> None:
    with pytest.raises(ValueError, match="expected 12"):
        bio_01(monthly_temp_c=[20.0] * n)


@pytest.mark.parametrize("n", [0, 1, 11, 13])
def test_length_must_be_12_precip(n: int) -> None:
    with pytest.raises(ValueError, match="expected 12"):
        bio_12(monthly_precip_mm=[100.0] * n)


def test_bio_01_success() -> None:
    assert is_success(bio_01(monthly_temp_c=_TEMP))
