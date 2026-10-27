"""FactRow model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agri_core.models.fact import FactRow

pytestmark = pytest.mark.unit


def _base(**kw):
    d = dict(
        fact_id="F01234567890",
        taxon_id="T012345678",
        parameter="soil_ph",
        phase=None,
        value={"shape": "unknown", "reason": "test"},
        scope={},
        provenance_kind="curated",
        src=["S001"],
        dataset_id=None,
        locator="page 42, table 2",
        evidence="A",
        status="draft",
        reviewed_by=None,
        reviewed_at=None,
        superseded_by=None,
    )
    d.update(kw)
    return d


# --- minimal valid ---


def test_fact_minimal_valid() -> None:
    row = FactRow(**_base())
    assert row.parameter == "soil_ph"
    assert row.evidence == "A"
    assert row.status == "draft"


def test_fact_scope_defaults_to_empty_dict() -> None:
    row = FactRow(**_base(scope={}))
    assert row.scope == {}


def test_fact_scope_accepts_dict() -> None:
    row = FactRow(**_base(scope={"country": ["ID"], "elevation_m": [0, 500]}))
    assert row.scope["country"] == ["ID"]


# --- provenance_kind cross-rules ---


def test_imported_requires_dataset() -> None:
    with pytest.raises(ValidationError, match="imported requires dataset_id"):
        FactRow(
            **_base(
                provenance_kind="imported",
                dataset_id=None,
                locator=None,
                src=["S001"],
                evidence="C",
            )
        )


def test_imported_with_dataset_ok() -> None:
    row = FactRow(
        **_base(provenance_kind="imported", dataset_id="D012345678", locator=None, evidence="C")
    )
    assert row.provenance_kind == "imported"


def test_imported_evidence_a_rejected() -> None:
    with pytest.raises(ValidationError, match="imported allows evidence C or D only"):
        FactRow(
            **_base(provenance_kind="imported", dataset_id="D012345678", locator=None, evidence="A")
        )


def test_imported_evidence_b_rejected() -> None:
    with pytest.raises(ValidationError, match="imported allows evidence C or D only"):
        FactRow(
            **_base(provenance_kind="imported", dataset_id="D012345678", locator=None, evidence="B")
        )


def test_imported_evidence_c_ok() -> None:
    FactRow(
        **_base(provenance_kind="imported", dataset_id="D012345678", locator=None, evidence="C")
    )


def test_imported_evidence_d_ok() -> None:
    FactRow(
        **_base(provenance_kind="imported", dataset_id="D012345678", locator=None, evidence="D")
    )


def test_derived_requires_dataset() -> None:
    with pytest.raises(ValidationError, match="derived requires dataset_id"):
        FactRow(**_base(provenance_kind="derived", dataset_id=None, locator="page 1", evidence="A"))


def test_derived_with_dataset_ok() -> None:
    FactRow(**_base(provenance_kind="derived", dataset_id="D012345678", locator=None, evidence="A"))


def test_curated_requires_locator() -> None:
    with pytest.raises(ValidationError, match="curated requires locator"):
        FactRow(
            **_base(
                provenance_kind="curated", locator=None, dataset_id=None, src=["S001"], evidence="A"
            )
        )


# --- status cross-rules ---


def test_status_reviewed_requires_reviewed_by() -> None:
    with pytest.raises(ValidationError, match="requires reviewed_by"):
        FactRow(**_base(status="reviewed", reviewed_by=None, reviewed_at="2026-10-24"))


def test_status_reviewed_requires_reviewed_at() -> None:
    with pytest.raises(ValidationError, match="requires reviewed_at"):
        FactRow(**_base(status="reviewed", reviewed_by="R001", reviewed_at=None))


def test_status_approved_requires_both() -> None:
    with pytest.raises(ValidationError, match="requires reviewed_by"):
        FactRow(**_base(status="approved", reviewed_by=None, reviewed_at=None))


def test_status_reviewed_with_both_ok() -> None:
    FactRow(**_base(status="reviewed", reviewed_by="R001", reviewed_at="2026-10-24"))


def test_status_draft_no_reviewed_ok() -> None:
    FactRow(**_base(status="draft"))


# --- src/dataset_id at least one ---


def test_no_src_no_dataset_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one of src or dataset_id"):
        FactRow(**_base(src=None, dataset_id=None))


# --- field validators ---


def test_phase_empty_rejected() -> None:
    with pytest.raises(ValidationError, match="phase must be non-empty"):
        FactRow(**_base(phase=""))


def test_reviewed_by_empty_rejected() -> None:
    with pytest.raises(ValidationError, match="reviewed_by items must be non-empty"):
        FactRow(**_base(reviewed_by=""))


def test_parameter_bad_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(parameter="SoilPH"))


def test_fact_id_bad_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(fact_id="X0123456789"))


def test_taxon_id_bad_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(taxon_id="X012345678"))


# --- superseded_by ---


def test_superseded_by_optional() -> None:
    row = FactRow(**_base(superseded_by=None))
    assert row.superseded_by is None


def test_superseded_by_accepts_fact_id() -> None:
    row = FactRow(**_base(superseded_by="F99999999999"))
    assert row.superseded_by == "F99999999999"


# --- immutability ---


def test_fact_frozen() -> None:
    row = FactRow(**_base())
    with pytest.raises((ValidationError, TypeError)):
        row.parameter = "other"  # type: ignore[misc]


def test_fact_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        FactRow(**_base(extra="boom"))
