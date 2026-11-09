"""threshold_index: registry engine tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agri_core.climate import threshold_index
from agri_core.models import InsufficientInput, Result, is_success

pytestmark = pytest.mark.unit

_BASE = date(2026, 1, 1)
_DATES7 = [_BASE + timedelta(days=i) for i in range(7)]
_TMIN = [5.0, 3.0, 10.0, -2.0, -1.0, 15.0, 20.0]
_TMAX = [15.0, 25.0, 30.0, 20.0, 40.0, 38.0, 15.0]
_PRECIP = [0.0, 5.0, 0.0, 0.0, 12.0, 0.0, 2.0]


def _v(o: object) -> float:
    assert isinstance(o, Result), f"not Result: {o!r}"
    return o.value


# ─── count / max_run ───


def test_frost_days() -> None:
    out = threshold_index(index_name="frost_days", dates=_DATES7, values=_TMIN)
    # Tmin < 0: idx 3 (-2), idx 4 (-1) => 2
    assert _v(out) == 2.0
    assert out.unit == "day"


def test_heat_days() -> None:
    out = threshold_index(index_name="heat_days", dates=_DATES7, values=_TMAX)
    # Tmax > 35: idx 4 (40), idx 5 (38) => 2
    assert _v(out) == 2.0


def test_dry_days() -> None:
    out = threshold_index(index_name="dry_days", dates=_DATES7, values=_PRECIP)
    # precip < 1: idx 0, 2, 3, 5 => 4
    assert _v(out) == 4.0


def test_wet_days() -> None:
    out = threshold_index(index_name="wet_days", dates=_DATES7, values=_PRECIP)
    # precip >= 1: idx 1, 4, 6 => 3
    assert _v(out) == 3.0


def test_frost_spell_max() -> None:
    out = threshold_index(index_name="frost_spell_max", dates=_DATES7, values=_TMIN)
    # Tmin < 0 at idx 3, 4 => max run 2
    assert _v(out) == 2.0


def test_heat_spell_max() -> None:
    out = threshold_index(index_name="heat_spell_max", dates=_DATES7, values=_TMAX)
    # Tmax > 35 at idx 4, 5 => max run 2
    assert _v(out) == 2.0


def test_dry_spell_max() -> None:
    out = threshold_index(index_name="dry_spell_max", dates=_DATES7, values=_PRECIP)
    # precip < 1: runs {0}, {2,3}, {5} => max run 2
    assert _v(out) == 2.0


def test_wet_spell_max() -> None:
    out = threshold_index(index_name="wet_spell_max", dates=_DATES7, values=_PRECIP)
    # precip >= 1: runs {1}, {4}, {6} => max run 1
    assert _v(out) == 1.0


# ─── rolling sums ───


def test_rolling_sum_7d_max() -> None:
    out = threshold_index(index_name="rolling_sum_7d_max", dates=_DATES7, values=_PRECIP)
    # Only 7 days available, window=7 → sum of all = 19
    assert _v(out) == 19.0
    assert out.unit == "millimeter"


def test_rolling_sum_30d_insufficient() -> None:
    out = threshold_index(index_name="rolling_sum_30d_max", dates=_DATES7, values=_PRECIP)
    assert isinstance(out, InsufficientInput)
    assert any("series_length_7_lt_window_30" in m for m in out.missing)


# ─── aggregates ───


def test_precip_total() -> None:
    out = threshold_index(index_name="precip_total", dates=_DATES7, values=_PRECIP)
    assert _v(out) == 19.0


def test_temp_min() -> None:
    out = threshold_index(index_name="temp_min", dates=_DATES7, values=_TMIN)
    assert _v(out) == -2.0


def test_temp_max() -> None:
    out = threshold_index(index_name="temp_max", dates=_DATES7, values=_TMAX)
    assert _v(out) == 40.0


# ─── threshold_override ───


def test_threshold_override() -> None:
    out = threshold_index(
        index_name="frost_days",
        dates=_DATES7,
        values=_TMIN,
        threshold_override=-1.5,
    )
    # Tmin < -1.5: only idx 3 (-2) => 1
    assert _v(out) == 1.0
    codes = {a.code for a in out.assumptions}
    assert "threshold_override_applied" in codes


def test_threshold_default_assumption() -> None:
    out = threshold_index(index_name="frost_days", dates=_DATES7, values=_TMIN)
    codes = {a.code for a in out.assumptions}
    assert "threshold_default_from_registry" in codes


# ─── errors / refusals ───


def test_unknown_index_insufficient() -> None:
    out = threshold_index(index_name="not_a_real_index", dates=_DATES7, values=_TMIN)
    assert isinstance(out, InsufficientInput)
    assert any("unknown_index" in m for m in out.missing)


def test_gap_in_dates_insufficient() -> None:
    dates = [date(2026, 1, 1), date(2026, 1, 3), date(2026, 1, 4)]
    out = threshold_index(index_name="frost_days", dates=dates, values=[-1.0, -2.0, -3.0])
    assert isinstance(out, InsufficientInput)
    assert any("gap_between" in m for m in out.missing)


def test_empty_series_insufficient() -> None:
    out = threshold_index(index_name="frost_days", dates=[], values=[])
    assert isinstance(out, InsufficientInput)
    assert "empty_series" in out.missing


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        threshold_index(index_name="frost_days", dates=_DATES7, values=[1.0, 2.0])


def test_success_marker() -> None:
    assert is_success(threshold_index(index_name="frost_days", dates=_DATES7, values=_TMIN))
