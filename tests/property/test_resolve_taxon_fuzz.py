"""Hypothesis fuzz for ``resolve_taxon`` (M8 review G11).

Two invariants proved over arbitrary Unicode:

1. **No unexpected exception.** Any input up to the G9 boundary (200 chars
   + a small margin) returns one of ``TaxonOk`` / ``Ambiguous`` /
   ``Unknown`` — never an unexpected exception, never a hang, never an
   outcome outside the documented set.

2. **Length guard is total.** Any input over the G9 boundary is rejected
   with ``Unknown(code="input_too_long")`` regardless of content (Unicode,
   ASCII, control chars, RTL, etc.).

The "no fuzzy match" invariant from the review is covered separately in
``tests/contract/test_resolve_taxon.py`` (typo -> ``no_match``), so this
file does not duplicate it.

Profile note: ``tests/conftest.py`` registers Hypothesis with
``deadline=None``, which is required for CI flake tolerance. Settings
here override ``max_examples`` to keep runtime under ~5s per file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agri_core.models.dictionary import Dictionary
from agri_core.models.name import NameRow
from agri_core.models.refusals import Ambiguous, Unknown
from agri_core.models.taxon import TaxonRow
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.registry import TaxonOk, resolve_taxon

pytestmark = pytest.mark.property

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")

# G9 boundary; keep +50 margin so the strategy exercises both the
# "within bound" and "just over bound" paths.
_MAX_INPUT = 200
_INPUT_MAX = _MAX_INPUT + 50


def _make_ks() -> InMemoryKnowledgeSet:
    """Small pack with two taxa so some fuzz inputs actually resolve."""
    manifest = PackManifest.model_validate(
        {
            "name": "fuzz",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    taxa = [
        TaxonRow(
            taxon_id="T000000001",
            rank="species",
            scientific_name="Testus annualis",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        ),
        TaxonRow(
            taxon_id="T000000002",
            rank="species",
            scientific_name="Alius perennis",
            organism_group="vascular_plant",
            archetype="perennial",
            uses=["ornamental"],
            traits=[],
            src=["S001"],
        ),
    ]
    names = [
        NameRow(
            taxon_id="T000000001",
            name="shared common",
            language="id",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
        NameRow(
            taxon_id="T000000002",
            name="shared common",
            language="en",
            script="Latn",
            kind="common",
            preferred=False,
            src=["S001"],
        ),
    ]
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "0" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        taxa=taxa,
        names=names,
        sources=(),
    )


_KS = _make_ks()


# ---- property 1: arbitrary short text never crashes ----------------------


@given(name=st.text(min_size=0, max_size=_INPUT_MAX))
@settings(max_examples=100, deadline=None, derandomize=True)
def test_arbitrary_text_never_crashes(name: str) -> None:
    """Any ``str`` up to ``_INPUT_MAX`` resolves or returns a valid ``Unknown``.

    "Valid ``Unknown``" means ``code`` in ``{"empty_input",
    "input_too_long", "no_match"}`` — the three codes ``resolve_taxon``
    may emit. Anything else (an uncaught exception, an ``AttributeError``,
    a ``pydantic.ValidationError`` bubbling out) would mean an input
    reached a path that was not defended.
    """
    r = resolve_taxon(_KS, name)
    assert isinstance(r, (TaxonOk, Ambiguous, Unknown)), (
        f"unexpected outcome type {type(r).__name__} for {name!r}"
    )
    if isinstance(r, Unknown):
        assert r.code in {"empty_input", "input_too_long", "no_match"}, (
            f"unexpected Unknown.code {r.code!r} for {name!r}"
        )


# ---- property 2: any over-bound input is rejected ------------------------


@given(name=st.text(min_size=_MAX_INPUT + 1, max_size=_INPUT_MAX))
@settings(max_examples=50, deadline=None, derandomize=True)
def test_long_text_always_input_too_long(name: str) -> None:
    """G9 invariant: ``len(name) > 200`` -> ``input_too_long``, any content."""
    r = resolve_taxon(_KS, name)
    assert isinstance(r, Unknown), f"expected Unknown for len={len(name)}, got {type(r).__name__}"
    assert r.code == "input_too_long", (
        f"expected input_too_long for len={len(name)}, got {r.code!r}"
    )
