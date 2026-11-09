"""irrigate_field_etc: numeric net irrigation depth."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.irrigation import irrigate_field_etc
from agri_core.models import Result, Unknown, is_success
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000001: kc = 0.65/1.05/0.75; ETc = Kc * ET0; net = max(0, ETc - P_eff)


def test_initial_no_precip(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="initial",
        et0_mm_day=5.0,
    )
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.65 * 5.0, abs=1e-9)
    assert out.unit == "millimeter/day"
    codes = {a.code for a in out.assumptions}
    assert "no_effective_precip_assumed_0" in codes


def test_midseason(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="midseason",
        et0_mm_day=5.0,
    )
    assert isinstance(out, Result)
    assert out.value == pytest.approx(1.05 * 5.0, abs=1e-9)


def test_late_season_with_precip(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="late_season",
        et0_mm_day=5.0,
        effective_precip_mm_day=2.0,
    )
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.75 * 5.0 - 2.0, abs=1e-9)
    codes = {a.code for a in out.assumptions}
    assert "no_effective_precip_assumed_0" not in codes


def test_precip_exceeds_etc_clamps_to_zero(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="initial",
        et0_mm_day=2.0,
        effective_precip_mm_day=5.0,
    )
    assert isinstance(out, Result)
    assert out.value == 0.0


def test_perennial_midseason(pack) -> None:
    # T000000007 kc midseason = 0.85
    out = irrigate_field_etc(
        pack,
        "T000000007",
        phase="midseason",
        et0_mm_day=4.0,
    )
    assert isinstance(out, Result)
    assert out.value == pytest.approx(0.85 * 4.0, abs=1e-9)


def test_unknown_phase_refused(pack) -> None:
    # T000000001 has no "development" kc phase
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="development",
        et0_mm_day=5.0,
    )
    # resolve_fact filters by allowed phase; if no kc for development,
    # returns unknown or insufficient_input
    assert not is_success(out)


def test_negative_et0_raises(pack) -> None:
    with pytest.raises(ValueError, match="et0_mm_day"):
        irrigate_field_etc(
            pack,
            "T000000001",
            phase="initial",
            et0_mm_day=-1.0,
        )


def test_negative_precip_raises(pack) -> None:
    with pytest.raises(ValueError, match="effective_precip_mm_day"):
        irrigate_field_etc(
            pack,
            "T000000001",
            phase="initial",
            et0_mm_day=5.0,
            effective_precip_mm_day=-1.0,
        )


def test_envelope(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T000000001",
        phase="midseason",
        et0_mm_day=5.0,
    )
    assert isinstance(out, Result)
    assert out.subject is not None
    assert out.subject.calculation == "irrigate_field_etc"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")
    assert out.provenance.fact_ids


def test_unknown_taxon_refused(pack) -> None:
    out = irrigate_field_etc(
        pack,
        "T999999999",
        phase="initial",
        et0_mm_day=5.0,
    )
    assert isinstance(out, Unknown)
