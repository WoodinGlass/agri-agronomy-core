"""Registry vs docs drift check (M7).

Every PackError subclass code and every Finding code emitted by a rule
in ``pack/validate.py`` must appear in ``PACK_FORMAT.md §Error code
reference``, and every documented code (except ``PACK_ERROR``, the base
class) must have an implementation.

If a new code lands without a doc line, ``test_all_*_codes_documented``
fails. If a doc line lands without an implementation,
``test_documented_codes_are_implemented`` fails. ``PACK_ERROR`` is
whitelisted as the documented base class that is never emitted as a
finding.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
ERRORS_PY = ROOT / "src/agri_core/pack/errors.py"
VALIDATE_PY = ROOT / "src/agri_core/pack/validate.py"
PACK_FORMAT = ROOT / "docs/PACK_FORMAT.md"

_BASE_CLASS_CODE = "PACK_ERROR"
"""The only documented code that is never instantiated."""


def _packerror_codes() -> set[str]:
    text = ERRORS_PY.read_text()
    return set(re.findall(r'code\s*=\s*"([A-Z][A-Z0-9_]+)"', text))


def _rule_finding_codes() -> set[str]:
    """AST scan: every ``Finding(code="...")`` literal in validate.py."""
    tree = ast.parse(VALIDATE_PY.read_text())
    codes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Finding":
                for kw in node.keywords:
                    if kw.arg == "code" and isinstance(kw.value, ast.Constant):
                        codes.add(kw.value.value)
    return codes


def _documented_codes() -> set[str]:
    """Codes in the PACK_FORMAT.md error table."""
    lines = PACK_FORMAT.read_text().splitlines()
    in_section = False
    codes: set[str] = set()
    for ln in lines:
        if ln.strip() == "## Error code reference":
            in_section = True
        elif in_section and ln.startswith("## "):
            break
        elif in_section:
            m = re.match(r"\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", ln)
            if m:
                codes.add(m.group(1))
    return codes


def test_all_packerror_codes_documented() -> None:
    missing = _packerror_codes() - _documented_codes()
    assert not missing, f"PackError codes not documented in PACK_FORMAT.md: {sorted(missing)}"


def test_all_rule_finding_codes_documented() -> None:
    missing = _rule_finding_codes() - _documented_codes()
    assert not missing, f"Rule Finding codes not documented in PACK_FORMAT.md: {sorted(missing)}"


def test_documented_codes_are_implemented() -> None:
    implemented = _packerror_codes() | _rule_finding_codes()
    orphan = _documented_codes() - implemented - {_BASE_CLASS_CODE}
    assert not orphan, f"Codes documented in PACK_FORMAT.md but not implemented: {sorted(orphan)}"


def test_pack_error_base_never_emitted_as_finding() -> None:
    assert _BASE_CLASS_CODE not in _rule_finding_codes(), (
        f"{_BASE_CLASS_CODE} is the base class; it must not appear as a Finding code"
    )


def _contract_files_with_contents() -> dict[str, str]:
    """All test files under tests/contract/, excluding the registry meta-test."""
    return {
        p.name: p.read_text(errors="replace")
        for p in (ROOT / "tests" / "contract").glob("*.py")
        if p.name != "test_finding_registry.py"
    }


def test_each_rule_code_has_contract_fixture() -> None:
    """Every rule-specific Finding code must be exercised by >=1 contract test.

    "Rule-specific" = a code emitted by a ``Finding(code=...)`` in
    ``pack/validate.py`` that is NOT already a ``PackError`` subclass code.
    The latter (e.g. ``PACK_INVALID``) appear from error->finding
    conversion and are covered by structural tests in
    ``test_load_knowledge_set.py`` and ``test_validation_report.py``.

    A rule without a fixture is untested dead code: CI cannot catch a
    regression. This test makes "add a rule, add a fixture" a mechanical
    requirement for every future rule.
    """
    rule_specific = _rule_finding_codes() - _packerror_codes()
    assert rule_specific, "no rule-specific codes found -- check AST scan"

    fixtures = _contract_files_with_contents()
    missing: dict[str, list[str]] = {}
    for code in sorted(rule_specific):
        hits = [name for name, text in fixtures.items() if code in text]
        if not hits:
            missing[code] = []

    assert not missing, (
        f"rule-specific codes without a contract fixture: {sorted(missing)}; "
        f"add a test in tests/contract/ that triggers each code"
    )
