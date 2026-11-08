"""PAR calculators: ppfd and dli."""

from __future__ import annotations

import pytest

from agri_core.climate import dli, ppfd
from agri_core.models import Result, is_success

pytestmark = pytest.mark.unit


def test_ppfd_typical() -> None:
    out = ppfd(par_w_m2=500.0)
    assert isinstance(out, Result)
    assert out.unit == "micromole/meter**2/second"
    assert out.method == "thimijan_heins_1983"
    # 4.57 * 500 = 2285
    assert out.value == pytest.approx(2285.0, abs=1.0)


def test_ppfd_zero() -> None:
    out = ppfd(par_w_m2=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-9)


def test_ppfd_assumption() -> None:
    out = ppfd(par_w_m2=500.0)
    assert isinstance(out, Result)
    codes = {a.code for a in out.assumptions}
    assert "par_to_ppfd_4_57" in codes


def test_ppfd_rejects_negative() -> None:
    with pytest.raises(ValueError, match="par_w_m2"):
        ppfd(par_w_m2=-10.0)


def test_dli_typical() -> None:
    out = dli(ppfd_umol=2285.0, photoperiod_hours=12.0)
    assert isinstance(out, Result)
    assert out.unit == "mole/meter**2/day"
    # 2285 * 12 * 3600 / 1e6 = 98.712
    assert out.value == pytest.approx(98.712, abs=0.05)


def test_dli_zero_photoperiod() -> None:
    out = dli(ppfd_umol=1000.0, photoperiod_hours=0.0)
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.0, abs=1e-9)


def test_dli_no_assumption() -> None:
    out = dli(ppfd_umol=1000.0, photoperiod_hours=12.0)
    assert isinstance(out, Result)
    assert out.assumptions == []


def test_dli_rejects_bad_photoperiod() -> None:
    with pytest.raises(ValueError, match="photoperiod_hours"):
        dli(ppfd_umol=1000.0, photoperiod_hours=25.0)
    with pytest.raises(ValueError, match="photoperiod_hours"):
        dli(ppfd_umol=1000.0, photoperiod_hours=-1.0)


def test_dli_rejects_negative_ppfd() -> None:
    with pytest.raises(ValueError, match="ppfd_umol"):
        dli(ppfd_umol=-1.0, photoperiod_hours=12.0)


def test_ppfd_and_dli_success() -> None:
    assert is_success(ppfd(par_w_m2=500.0))
    assert is_success(dli(ppfd_umol=2285.0, photoperiod_hours=12.0))
