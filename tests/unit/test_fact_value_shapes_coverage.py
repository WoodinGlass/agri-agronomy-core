"""Meta-test: every shape in the ``FactValue`` union has a fixture, and
each fixture validates against the discriminated union.

The fixture set is the oracle for the native Rust migration (M21). The
expected shape set is derived from ``FactValue`` itself, so adding a
shape without a fixture, or leaving an orphan fixture, fails this test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast, get_args

from pydantic import BaseModel, TypeAdapter

from agri_core.models.fact import FactValue

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "exports" / "fact_value_shapes"

_EXPECTED_SHAPE_COUNT = 8


def _union_members() -> tuple[type[BaseModel], ...]:
    """Every Pydantic model reachable from the ``FactValue`` union."""
    args = get_args(FactValue)
    assert args, "FactValue is not Annotated[Union[...], ...]"
    inner = args[0]
    members = get_args(inner)
    assert members, f"FactValue inner is not a Union: {inner!r}"
    return cast(tuple[type[BaseModel], ...], members)


def _shape_of_member(member: type[BaseModel]) -> str:
    """The single shape Literal carried by a ``FactValue`` member."""
    shape_field = member.model_fields.get("shape")
    assert shape_field is not None, f"{member.__name__} has no 'shape' field"
    lit = get_args(shape_field.annotation)
    assert len(lit) == 1, f"{member.__name__}.shape is not a 1-value Literal: {lit}"
    val = lit[0]
    assert isinstance(val, str), f"{member.__name__}.shape literal is not a str: {val!r}"
    return val


def _expected_shapes() -> set[str]:
    return {_shape_of_member(m) for m in _union_members()}


def _fixture_paths() -> list[Path]:
    return sorted(_FIXTURE_DIR.glob("*.json"))


def test_union_has_eight_shapes() -> None:
    """Silent removal or addition of a shape must fail loudly."""
    shapes = _expected_shapes()
    assert len(shapes) == _EXPECTED_SHAPE_COUNT, (
        f"expected {_EXPECTED_SHAPE_COUNT} shapes, got {len(shapes)}: {sorted(shapes)}"
    )


def test_fixture_directory_exists() -> None:
    assert _FIXTURE_DIR.is_dir(), f"fixture directory missing: {_FIXTURE_DIR}"


def test_every_shape_has_fixture() -> None:
    """Every union shape is represented by a committed JSON fixture."""
    present = {p.stem for p in _fixture_paths()}
    missing = _expected_shapes() - present
    assert not missing, f"shapes without fixture: {sorted(missing)}"


def test_no_orphan_fixtures() -> None:
    """Every fixture corresponds to a shape still in the union."""
    present = {p.stem for p in _fixture_paths()}
    orphans = present - _expected_shapes()
    assert not orphans, f"fixtures for unknown shapes: {sorted(orphans)}"


def test_fixture_shape_matches_filename() -> None:
    """The ``shape`` value inside a fixture equals the filename stem."""
    mismatches = []
    for fp in _fixture_paths():
        data = json.loads(fp.read_text(encoding="utf-8"))
        if data.get("shape") != fp.stem:
            mismatches.append((fp.name, data.get("shape")))
    assert not mismatches, f"shape mismatch: {mismatches}"


def test_fixtures_validate_against_fact_value() -> None:
    """Each fixture parses cleanly with the discriminated ``TypeAdapter``."""
    adapter = TypeAdapter(FactValue)
    failures = []
    for fp in _fixture_paths():
        try:
            adapter.validate_python(json.loads(fp.read_text(encoding="utf-8")))
        except Exception as exc:
            failures.append((fp.name, str(exc)))
    assert not failures, f"fixtures that do not validate: {failures}"
