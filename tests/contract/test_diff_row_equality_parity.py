"""Row-equality parity between native and Python diff (HP#5).

Two invariants must hold for the Rust core to give the same verdict
as the Python oracle:

1. Every field of ``FactRow`` (except the identity ``fact_id``) is
   classified as either "acceptable" or "violation" by
   ``_ACCEPTABLE_FIELDS`` / ``_VIOLATION_FIELDS``. A new Pydantic
   field without a matching bucket would silently never register a
   change; the meta-assert catches that drift.
2. Mutating exactly one field yields exactly one ``fields_changed``
   entry with that field name, both from Rust and Python.

Meta-asserts are pure Python (always run). Per-field parity needs
the ``exp-diff`` Cargo feature; those tests skip cleanly when
``_native.diff_loaded`` is absent (Colab default).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from agri_core import _native
from agri_core.models.fact import FactRow, ScalarValue
from agri_core.models.taxon import TaxonRow
from agri_core.pack.diff import (
    _ACCEPTABLE_FIELDS,
    _VIOLATION_FIELDS,
    DiffReport,
    _diff_config_args,
    _render_diff_payload,
)

pytestmark = pytest.mark.contract

_NATIVE_FN = getattr(_native, "diff_loaded", None)

_SKIP_NO_NATIVE = pytest.mark.skipif(
    _NATIVE_FN is None,
    reason="exp-diff feature off (rebuild with --features exp-diff)",
)


def _base_taxon() -> TaxonRow:
    return TaxonRow(
        taxon_id="T000000001",
        rank="species",
        scientific_name="Testus testus",
        accepted_name=None,
        organism_group="vascular_plant",
        archetype="annual",
        uses=["vegetable"],
        traits=[],
        parent_id=None,
        external_ids=None,
        src=["S001"],
        dataset_id=None,
    )


def _base_fact(**overrides: object) -> FactRow:
    data: dict[str, Any] = dict(
        fact_id="F00000000001",
        taxon_id="T000000001",
        parameter="gdd_base",
        phase=None,
        value=ScalarValue(shape="scalar", unit="degree_Celsius", value=1.0),
        scope={},
        provenance_kind="curated",
        src=["S001"],
        dataset_id="D012345678",
        locator="test-locator",
        evidence="A",
        status="draft",
        reviewed_by=None,
        reviewed_at=None,
        superseded_by=None,
    )
    data.update(overrides)
    return FactRow(**data)


def _mutated_fact(field_name: str) -> FactRow:
    mappers: dict[str, FactRow] = {
        "status": _base_fact(status="imported"),
        "evidence": _base_fact(evidence="B"),
        "reviewed_by": _base_fact(reviewed_by=["R001"]),
        "reviewed_at": _base_fact(reviewed_at=date(2026, 1, 1)),
        "locator": _base_fact(locator="other-locator"),
        "superseded_by": _base_fact(superseded_by="F00000000002"),
        "src": _base_fact(src=["S002"]),
        "dataset_id": _base_fact(dataset_id="D876543210"),
        "provenance_kind": _base_fact(provenance_kind="derived"),
        "value": _base_fact(
            value=ScalarValue(
                shape="scalar",
                unit="degree_Celsius",
                value=2.0,
            )
        ),
        "scope": _base_fact(scope={"country": ["ID"]}),
        "parameter": _base_fact(parameter="gdd_upper"),
        "taxon_id": _base_fact(taxon_id="T000000002"),
        "phase": _base_fact(phase="flowering"),
    }
    if field_name not in mappers:
        raise AssertionError(f"no mutation defined for field: {field_name}")
    return mappers[field_name]


_HASH = "sha256:" + "0" * 64


def _call_native(
    old_taxa: list[TaxonRow],
    old_facts: list[FactRow],
    new_taxa: list[TaxonRow],
    new_facts: list[FactRow],
) -> DiffReport:
    if _NATIVE_FN is None:
        raise AssertionError("_call_native called without native")
    acc, vio, prot = _diff_config_args()
    payload = _NATIVE_FN(
        [t.model_dump(mode="json") for t in old_taxa],
        [f.model_dump(mode="json") for f in old_facts],
        None,
        _HASH,
        [t.model_dump(mode="json") for t in new_taxa],
        [f.model_dump(mode="json") for f in new_facts],
        None,
        _HASH,
        acc,
        vio,
        prot,
    )
    return _render_diff_payload(payload)


# ---- meta-asserts (no native needed) ----


def test_fact_row_fields_cover_acceptable_and_violation() -> None:
    covered = set(FactRow.model_fields) - {"fact_id"}
    assert covered == _ACCEPTABLE_FIELDS | _VIOLATION_FIELDS


def test_taxon_row_fields_full_coverage() -> None:
    expected = {
        "taxon_id",
        "rank",
        "scientific_name",
        "accepted_name",
        "organism_group",
        "archetype",
        "uses",
        "traits",
        "parent_id",
        "external_ids",
        "src",
        "dataset_id",
    }
    assert set(TaxonRow.model_fields) == expected


# ---- per-field parity (native required) ----


@_SKIP_NO_NATIVE
@pytest.mark.parametrize(
    "field_name",
    sorted(_ACCEPTABLE_FIELDS | _VIOLATION_FIELDS),
)
def test_per_field_parity(field_name: str) -> None:
    base = _base_fact()
    mutated = _mutated_fact(field_name)
    tx = _base_taxon()
    report = _call_native([tx], [base], [tx], [mutated])
    assert not report.identical
    assert len(report.facts_changed) == 1
    assert field_name in report.facts_changed[0].fields_changed


# ---- edge cases ----


@_SKIP_NO_NATIVE
def test_scope_permutation_equivalent() -> None:
    base = _base_fact(scope={"country": ["ID"], "system": "field"})
    mutated = _base_fact(scope={"system": "field", "country": ["ID"]})
    tx = _base_taxon()
    report = _call_native([tx], [base], [tx], [mutated])
    assert report.identical
    assert report.facts_changed == ()


@_SKIP_NO_NATIVE
def test_scalar_int_vs_float_json_equivalent() -> None:
    base_json = _base_fact().model_dump(mode="json")
    mutated_json = _base_fact().model_dump(mode="json")
    mutated_json["value"]["value"] = 1
    tx_json = _base_taxon().model_dump(mode="json")
    if _NATIVE_FN is None:
        raise AssertionError("native required")
    acc, vio, prot = _diff_config_args()
    payload = _NATIVE_FN(
        [tx_json],
        [base_json],
        None,
        _HASH,
        [tx_json],
        [mutated_json],
        None,
        _HASH,
        acc,
        vio,
        prot,
    )
    report = _render_diff_payload(payload)
    assert report.identical
