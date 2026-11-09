"""check_water_quality: EC and temperature limit check against pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core.media import check_water_quality
from agri_core.models import CategoricalResult, Unknown
from agri_core.pack import load_knowledge_set

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def pack():
    return load_knowledge_set(SAMPLE, allow_synthetic=True)


# T000000002: water_ec_max = 2.0 dS/m, water_temp_max = 28.0 C
# T000000004: water_temp_max is UnknownValue; water_ec_max absent


def test_ok(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "ok"


def test_at_limit_is_ok(pack) -> None:
    # ec == max and temp == max are not exceedances (strict comparison)
    out = check_water_quality(pack, "T000000002", ec_ds_m=2.0, temp_c=28.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "ok"


def test_exceed_ec(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=2.5, temp_c=25.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "exceed_ec"


def test_exceed_temp(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=30.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "exceed_temp"


def test_exceed_both(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=2.5, temp_c=30.0)
    assert isinstance(out, CategoricalResult)
    assert out.category == "exceed_both"


def test_unknown_temperature_limit_refuses(pack) -> None:
    # T000000004 F13 is an UnknownValue for water_temp_max.
    out = check_water_quality(pack, "T000000004", ec_ds_m=1.0, temp_c=20.0)
    assert isinstance(out, Unknown)
    assert out.code is None  # value_unknown not registered yet


def test_unknown_taxon_refused(pack) -> None:
    out = check_water_quality(pack, "T999999999", ec_ds_m=1.0, temp_c=20.0)
    assert isinstance(out, Unknown)


def test_negative_ec_raises(pack) -> None:
    with pytest.raises(ValueError, match="ec_ds_m"):
        check_water_quality(pack, "T000000002", ec_ds_m=-0.1, temp_c=25.0)


def test_envelope(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    assert isinstance(out, CategoricalResult)
    assert out.subject is not None
    assert out.subject.calculation == "check_water_quality"
    assert out.request_id is not None
    assert out.request_id.startswith("req_")
    assert len(out.provenance.fact_ids) == 2


def test_determinism(pack) -> None:
    a = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    b = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    assert isinstance(a, CategoricalResult)
    assert isinstance(b, CategoricalResult)
    assert a.request_id == b.request_id
    assert a.category == b.category


def test_label_present(pack) -> None:
    out = check_water_quality(pack, "T000000002", ec_ds_m=1.5, temp_c=25.0)
    assert isinstance(out, CategoricalResult)
    assert out.label == "OK"
