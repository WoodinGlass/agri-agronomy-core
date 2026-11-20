"""Mutation-pair parity between native and Python diff (HP#7).

Instead of generating two independent packs (which would produce nearly
disjoint fact-id sets and never exercise the changed/violation paths),
this test generates a base fact list and applies N in-place mutations:

- change_status / change_value / change_scope / change_parameter
- change_phase / change_superseded_by / change_evidence

For each example, the Python ``diff_packs`` (eager, in-memory) and the
native ``_native.diff_loaded`` must give identical ``DiffReport`` content:
the same ``identical`` flag, the same fact_id sets under ``facts_changed``,
the same per-fact ``fields_changed`` and ``classification``, and the
same (kind, entity_id) set under ``violations``.

Fact-level add/remove is covered by ``tests/contract/test_diff.py``
(existing) and by ``tests/contract/test_diff_across_schema.py``;
taxon-level add/remove by ``test_diff_taxon_added_not_violation`` /
``test_diff_taxon_removed_is_violation``. This test focuses on the
space the other tests do not exercise: multi-mutation pairs where the
classification+fields matrix decides the violation set.

Requires the ``exp-diff`` Cargo feature; every native test skips cleanly
when ``_native.diff_loaded`` is absent. One additional pure-Python
smoke test verifies the KnowledgeSet-building helper so a helper bug
does not hide until CI.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agri_core import _native
from agri_core.models.dictionary import Dictionary
from agri_core.models.fact import FactRow, ScalarValue
from agri_core.models.taxon import TaxonRow
from agri_core.pack.diff import (
    DiffReport,
    _diff_config_args,
    _render_diff_payload,
    diff_packs,
)
from agri_core.pack.knowledge_set import (
    InMemoryKnowledgeSet,
    KnowledgeSet,
)
from agri_core.pack.loader import _default_dictionary
from agri_core.pack.manifest import PackManifest

pytestmark = [pytest.mark.property, pytest.mark.contract]

_NATIVE_FN = getattr(_native, "diff_loaded", None)
_SKIP_NO_NATIVE = pytest.mark.skipif(
    _NATIVE_FN is None,
    reason="exp-diff feature off (rebuild with --features exp-diff)",
)

_HASH = "sha256:" + "0" * 64
_INITIAL_FACT_IDS = ["F00000000001", "F00000000002", "F00000000003"]
_MUTATION_OPS = [
    "change_status",
    "change_value",
    "change_scope",
    "change_parameter",
    "change_phase",
    "change_superseded_by",
    "change_evidence",
]


@lru_cache(maxsize=1)
def _dictionary() -> Dictionary:
    return _default_dictionary()


def _manifest() -> PackManifest:
    return PackManifest(
        name="mutation-test",
        version="1.0.0",
        schema_version=1,
        engine_min="0.0.0",
        dictionary_min="1.0.0",
        synthetic=True,
    )


def _base_taxon(tid: str = "T000000001", name: str = "Testus testus") -> TaxonRow:
    return TaxonRow(
        taxon_id=tid,
        rank="species",
        scientific_name=name,
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


def _base_fact(fid: str, tid: str = "T000000001", **overrides: Any) -> FactRow:
    data: dict[str, Any] = dict(
        fact_id=fid,
        taxon_id=tid,
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


def _build_ks(*, taxa: list[TaxonRow], facts: list[FactRow]) -> KnowledgeSet:
    d = _dictionary()
    return InMemoryKnowledgeSet.from_rows(
        manifest=_manifest(),
        pack_hash=_HASH,
        dictionary_version=d.version,
        dictionary=d,
        verified=False,
        taxa=taxa,
        facts=facts,
    )


def _call_native(
    *,
    old_taxa: list[TaxonRow],
    old_facts: list[FactRow],
    new_taxa: list[TaxonRow],
    new_facts: list[FactRow],
) -> DiffReport:
    if _NATIVE_FN is None:
        raise AssertionError("native required")
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


def _assert_reports_match(py: DiffReport, native: DiffReport) -> None:
    assert py.identical == native.identical
    assert sorted(fc.fact_id for fc in py.facts_changed) == sorted(
        fc.fact_id for fc in native.facts_changed
    )
    assert sorted((v.kind, v.entity_id) for v in py.violations) == sorted(
        (v.kind, v.entity_id) for v in native.violations
    )
    py_by_id = {fc.fact_id: fc for fc in py.facts_changed}
    native_by_id = {fc.fact_id: fc for fc in native.facts_changed}
    assert set(py_by_id) == set(native_by_id)
    for fid, py_fc in py_by_id.items():
        native_fc = native_by_id[fid]
        assert py_fc.classification == native_fc.classification
        assert tuple(py_fc.fields_changed) == tuple(native_fc.fields_changed)


@st.composite
def _mutated_facts(
    draw: st.DrawFn,
) -> tuple[list[FactRow], list[FactRow]]:
    base = [_base_fact(fid) for fid in _INITIAL_FACT_IDS]
    mutated = list(base)
    n_ops = draw(st.integers(min_value=0, max_value=3))
    for _ in range(n_ops):
        op = draw(st.sampled_from(_MUTATION_OPS))
        idx = draw(st.integers(min_value=0, max_value=len(mutated) - 1))
        old = mutated[idx]
        if op == "change_status":
            f = old.model_copy(update={"status": "reviewed"})
        elif op == "change_value":
            f = old.model_copy(
                update={"value": ScalarValue(shape="scalar", unit="degree_Celsius", value=2.0)}
            )
        elif op == "change_scope":
            f = old.model_copy(update={"scope": {"country": ["ID"]}})
        elif op == "change_parameter":
            f = old.model_copy(update={"parameter": "gdd_upper"})
        elif op == "change_phase":
            f = old.model_copy(update={"phase": "flowering"})
        elif op == "change_superseded_by":
            f = old.model_copy(update={"superseded_by": "F99999999999"})
        elif op == "change_evidence":
            f = old.model_copy(update={"evidence": "B"})
        else:
            raise AssertionError("unknown mutation op: " + op)
        mutated[idx] = f
    return base, mutated


@_SKIP_NO_NATIVE
@settings(max_examples=200, deadline=None)
@given(pair=_mutated_facts())
def test_mutation_parity(
    pair: tuple[list[FactRow], list[FactRow]],
) -> None:
    base_facts, mutated_facts = pair
    tx = _base_taxon()
    py = diff_packs(
        _build_ks(taxa=[tx], facts=base_facts),
        _build_ks(taxa=[tx], facts=mutated_facts),
    )
    native = _call_native(
        old_taxa=[tx],
        old_facts=base_facts,
        new_taxa=[tx],
        new_facts=mutated_facts,
    )
    _assert_reports_match(py, native)


def test_build_ks_helper_smoke() -> None:
    """The KS wrapper has to work even without native; catches helper bugs
    in Colab so they do not surface only in CI.
    """
    tx = _base_taxon()
    f = _base_fact("F00000000001")
    ks = _build_ks(taxa=[tx], facts=[f])
    assert type(ks).__name__ == "InMemoryKnowledgeSet"
    assert len(list(ks.taxa())) == 1
    assert len(list(ks.facts())) == 1
