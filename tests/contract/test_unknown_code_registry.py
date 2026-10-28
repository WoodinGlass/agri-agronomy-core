"""Drift test: ``Unknown.code`` registry vs. emitted codes vs. ADR-004.

The registry at ``schema/unknown_code_registry.json`` declares every
``Unknown.code`` value the resolver may emit. Each entry carries a
``status``:

- ``active`` -- the code is already emitted by the resolver in
  ``src/agri_core/``; the drift test asserts it is present in source.
- ``planned`` -- the code is reserved for a later PR and must NOT be
  emitted yet; the drift test asserts it is absent from source.

If a ``planned`` code appears in source, its registry entry must be
promoted to ``active``. If an emitted code is not in the registry, the
registry must be extended. Both directions are enforced.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO / "schema" / "unknown_code_registry.json"
_SRC_DIR = _REPO / "src" / "agri_core"
_ADR_PATH = _REPO / "docs" / "decisions" / "ADR-004-resolution-policy.md"

_CODE_PATTERN = __import__("re").compile(r"^[a-z][a-z0-9_]*$")
_VALID_STATUSES = {"active", "planned"}


def _load_registry() -> dict:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def _emitted_codes() -> set[str]:
    """Every ``Unknown(code="...")`` literal emitted from ``src/agri_core/``.

    Uses AST so docstrings and comments cannot accidentally register a
    code. Recognizes both ``Unknown(...)`` (via Name) and
    ``<module>.Unknown(...)`` (via Attribute) call forms.
    """
    found: set[str] = set()
    for path in _SRC_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            is_unknown = (isinstance(f, ast.Name) and f.id == "Unknown") or (
                isinstance(f, ast.Attribute) and f.attr == "Unknown"
            )
            if not is_unknown:
                continue
            for kw in node.keywords:
                if kw.arg == "code" and isinstance(kw.value, ast.Constant):
                    val = kw.value.value
                    if isinstance(val, str):
                        found.add(val)
    return found


# ---- tests ----------------------------------------------------------------


def test_registry_schema_valid() -> None:
    reg = _load_registry()
    assert reg["version"] == 1
    assert isinstance(reg["codes"], list)
    assert len(reg["codes"]) > 0

    seen: set[str] = set()
    for entry in reg["codes"]:
        assert isinstance(entry, dict), f"entry not dict: {entry!r}"
        for key in ("code", "status", "description"):
            assert key in entry, f"missing {key!r} in {entry!r}"
        assert isinstance(entry["code"], str)
        assert _CODE_PATTERN.match(entry["code"]), (
            f"code {entry['code']!r} does not match ^[a-z][a-z0-9_]*$"
        )
        assert entry["status"] in _VALID_STATUSES, (
            f"status {entry['status']!r} not in {_VALID_STATUSES}"
        )
        assert isinstance(entry["description"], str)
        assert entry["description"]
        assert entry["code"] not in seen, f"duplicate code {entry['code']!r}"
        seen.add(entry["code"])


def test_active_codes_present_in_source() -> None:
    reg = _load_registry()
    active = {e["code"] for e in reg["codes"] if e["status"] == "active"}
    emitted = _emitted_codes()
    missing = active - emitted
    assert not missing, (
        f"active codes missing from source: {sorted(missing)}. "
        f"Either implement them or demote to 'planned'."
    )


def test_planned_codes_not_yet_in_source() -> None:
    reg = _load_registry()
    planned = {e["code"] for e in reg["codes"] if e["status"] == "planned"}
    emitted = _emitted_codes()
    leaked = planned & emitted
    assert not leaked, (
        f"planned codes already emitted in source: {sorted(leaked)}. "
        f"Promote them to 'active' in the registry."
    )


def test_every_emitted_code_registered() -> None:
    reg = _load_registry()
    registered = {e["code"] for e in reg["codes"]}
    emitted = _emitted_codes()
    unregistered = emitted - registered
    assert not unregistered, (
        f"emitted codes not in registry: {sorted(unregistered)}. "
        f"Add them to schema/unknown_code_registry.json."
    )


def test_planned_codes_documented_in_adr() -> None:
    reg = _load_registry()
    planned = [e["code"] for e in reg["codes"] if e["status"] == "planned"]
    adr = _ADR_PATH.read_text(encoding="utf-8")
    missing = [c for c in planned if c not in adr]
    assert not missing, f"planned codes not documented in ADR-004: {sorted(missing)}"
