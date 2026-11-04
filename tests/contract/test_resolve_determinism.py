"""Cross-process determinism for ``resolve_taxon`` and ``resolve_fact`` (G10).

Resolution output must be **byte-identical** across processes with
different ``PYTHONHASHSEED`` values. The resolver sorts every collection
it iterates (``sorted_ids``, ``sorted(alternatives.keys())``,
``sorted(set(winner.src))``), so there is no iteration over an unordered
set or dict whose order would depend on the hash seed. This test proves
that property by running the same probe in two subprocesses with seeds
``"1"`` and ``"2"`` (matching the existing determinism test in
``test_sqlite_build.py``) and comparing stdout byte-for-byte.

The probe covers three resolution paths that exercise different
collections:

- ``resolve_taxon`` → ``Ambiguous`` (multiple ``taxon_id`` sorted by ID);
- ``resolve_taxon`` → ``TaxonOk`` (single taxon, ``matched_via`` chosen);
- ``resolve_fact`` → ``FactResolved`` (winner + sorted ``alternatives``).

Each result is serialized via the outcome-specific ``TypeAdapter`` and
then ``canonical_json`` (sorted keys, compact separators), so two runs
that agree on the *values* will also agree byte-for-byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_DICT_PATH = _REPO / "dictionary" / "parameters.core.yaml"

_PROBE = textwrap.dedent(
    """
    import sys
    from datetime import date
    from pathlib import Path

    from agri_core.models.canonical import canonical_json
    from agri_core.models.dictionary import Dictionary
    from agri_core.models.fact import FactRow, ScalarValue
    from agri_core.models.name import NameRow
    from agri_core.models.taxon import TaxonRow
    from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
    from agri_core.pack.manifest import PackManifest
    from agri_core.registry import (
        FactOutcomeAdapter,
        TaxonOutcomeAdapter,
        resolve_fact,
        resolve_taxon,
    )

    DICT = Dictionary.load(Path(sys.argv[1]))
    manifest = PackManifest.model_validate(
        {
            "name": "det",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name=f"Testus {i}",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        )
        for i in range(3)
    ]
    names = [
        NameRow(
            taxon_id="T000000000",
            name="shared name",
            language="id",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
        NameRow(
            taxon_id="T000000001",
            name="shared name",
            language="en",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
    ]
    facts = [
        FactRow(
            fact_id=f"F{i:011d}",
            taxon_id="T000000000",
            parameter="soil_ph",
            phase=None,
            value=ScalarValue(shape="scalar", unit="pH", value=6.5),
            scope={},
            provenance_kind="curated",
            src=["S001"],
            locator="L",
            evidence="A",
            status="approved",
            reviewed_by=["r"],
            reviewed_at=date(2026, 1, 1),
            superseded_by=None,
        )
        for i in range(2)
    ]
    ks = InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=DICT.version,
        dictionary=DICT,
        taxa=taxa,
        names=names,
        facts=facts,
        sources=(),
    )

    r_ambig = resolve_taxon(ks, "shared name")
    r_ok = resolve_taxon(ks, "Testus 1")
    r_fact = resolve_fact(ks, "T000000000", "soil_ph")

    for r, adapter in (
        (r_ambig, TaxonOutcomeAdapter),
        (r_ok, TaxonOutcomeAdapter),
        (r_fact, FactOutcomeAdapter),
    ):
        print(canonical_json(adapter.dump_python(r, mode="json")).decode())
    """
).strip()


def _run_probe(seed: str) -> str:
    """Run the probe in a fresh process with the given PYTHONHASHSEED."""
    env = {**os.environ, "PYTHONHASHSEED": seed}
    r = subprocess.run(
        [sys.executable, "-c", _PROBE, str(_DICT_PATH)],
        capture_output=True,
        text=True,
        cwd=_REPO,
        env=env,
        timeout=60,
    )
    if r.returncode != 0:
        raise AssertionError(
            f"determinism probe failed (PYTHONHASHSEED={seed}):\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r.stdout


def test_resolution_deterministic_across_pythonhashseed() -> None:
    """G10: resolve_taxon and resolve_fact output is byte-identical across seeds.

    The probe resolves three paths (Ambiguous, TaxonOk, FactResolved)
    and prints one canonical JSON line per path. Two subprocesses with
    different ``PYTHONHASHSEED`` values must print the same bytes.
    """
    a = _run_probe("1")
    b = _run_probe("2")

    # Sanity: probe actually resolved something, not trivially identical empty output.
    lines = [ln for ln in a.splitlines() if ln.strip()]
    assert len(lines) == 3, f"expected 3 result lines, got {len(lines)}: {lines!r}"
    assert len(a) > 500, f"probe output suspiciously short: {len(a)} chars"

    # Status fields present in each result line (order per probe source).
    assert '"ambiguous"' in lines[0], f"line 0 not Ambiguous: {lines[0][:120]!r}"
    assert '"ok"' in lines[1], f"line 1 not TaxonOk: {lines[1][:120]!r}"
    assert '"ok"' in lines[2], f"line 2 not FactResolved: {lines[2][:120]!r}"

    # The determinism check: byte-identical across seeds.
    assert a == b, (
        "resolution output differs across PYTHONHASHSEED values; "
        "some code path iterates an unordered set/dict without sorting"
    )


def test_resolution_deterministic_repeat_in_process() -> None:
    """G10: same-process repeated calls produce identical JSON.

    Complements the cross-process test: catches accidental mutation of
    a shared pack or a cached list that would make two consecutive calls
    return different JSON even within one hash seed.
    """
    import json as _json
    from datetime import date

    from agri_core.models.canonical import canonical_json
    from agri_core.models.dictionary import Dictionary
    from agri_core.models.fact import FactRow, ScalarValue
    from agri_core.models.name import NameRow
    from agri_core.models.taxon import TaxonRow
    from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
    from agri_core.pack.manifest import PackManifest
    from agri_core.registry import (
        FactOutcomeAdapter,
        TaxonOutcomeAdapter,
        resolve_fact,
        resolve_taxon,
    )

    DICT = Dictionary.load(_DICT_PATH)
    manifest = PackManifest.model_validate(
        {
            "name": "det",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name=f"Testus {i}",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        )
        for i in range(3)
    ]
    names = [
        NameRow(
            taxon_id="T000000000",
            name="shared name",
            language="id",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
        NameRow(
            taxon_id="T000000001",
            name="shared name",
            language="en",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
    ]
    facts = [
        FactRow(
            fact_id=f"F{i:011d}",
            taxon_id="T000000000",
            parameter="soil_ph",
            phase=None,
            value=ScalarValue(shape="scalar", unit="pH", value=6.5),
            scope={},
            provenance_kind="curated",
            src=["S001"],
            locator="L",
            evidence="A",
            status="approved",
            reviewed_by=["r"],
            reviewed_at=date(2026, 1, 1),
            superseded_by=None,
        )
        for i in range(2)
    ]
    ks = InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=DICT.version,
        dictionary=DICT,
        taxa=taxa,
        names=names,
        facts=facts,
        sources=(),
    )

    def _dump(adapter, r):  # type: ignore[no-untyped-def]
        return canonical_json(adapter.dump_python(r, mode="json")).decode()

    a_ambig = _dump(TaxonOutcomeAdapter, resolve_taxon(ks, "shared name"))
    b_ambig = _dump(TaxonOutcomeAdapter, resolve_taxon(ks, "shared name"))
    assert a_ambig == b_ambig

    a_ok = _dump(TaxonOutcomeAdapter, resolve_taxon(ks, "Testus 1"))
    b_ok = _dump(TaxonOutcomeAdapter, resolve_taxon(ks, "Testus 1"))
    assert a_ok == b_ok

    a_fact = _dump(FactOutcomeAdapter, resolve_fact(ks, "T000000000", "soil_ph"))
    b_fact = _dump(FactOutcomeAdapter, resolve_fact(ks, "T000000000", "soil_ph"))
    assert a_fact == b_fact

    # Sanity: parsed JSON has no version drift in provenance.
    fact_json = _json.loads(a_fact)
    assert "provenance" in fact_json
    assert "resolution_policy_version" in fact_json["provenance"]
