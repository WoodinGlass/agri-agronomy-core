"""Golden diff fixtures (PR-G2).

For each case in ``_diff_golden.CASES``:

- ``test_golden[case]`` rebuilds the two-pack diff and compares against
  ``tests/golden/diff/<case>/expected.json``.
- ``test_regen_is_idempotent`` reruns ``scripts/gen_diff_golden.py``
  and asserts the committed fixtures do not change (the same pattern
  used by ``test_finding_drift.py`` for JSON schema regen).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _diff_golden import CASES, build_case

from agri_core.pack import load_knowledge_set  # noqa: F401  (reused via _diff_golden)

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "tests" / "golden" / "diff"


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden(case: str, tmp_path: Path) -> None:
    expected_path = GOLDEN_DIR / case / "expected.json"
    assert expected_path.is_file(), f"missing fixture: {expected_path}"

    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = build_case(case, tmp_path)

    assert actual == expected, (
        f"golden mismatch for {case!r}.\n"
        f"  regenerate with: python scripts/gen_diff_golden.py\n"
        f"  expected: {expected_path}"
    )


def test_regen_is_idempotent() -> None:
    before = {
        p.parent.name: p.read_text(encoding="utf-8") for p in GOLDEN_DIR.glob("*/expected.json")
    }
    assert before, "no golden fixtures found"

    result = subprocess.run(
        [sys.executable, "scripts/gen_diff_golden.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    after = {
        p.parent.name: p.read_text(encoding="utf-8") for p in GOLDEN_DIR.glob("*/expected.json")
    }
    assert before == after, (
        "regenerating golden fixtures changed them; "
        "either the golden fixtures were stale (rerun and commit) "
        "or DiffReport output drifted"
    )
