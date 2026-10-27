"""Regenerate golden diff fixtures.

Run from the repo root:

    python scripts/gen_diff_golden.py

Writes ``tests/golden/diff/<case>/expected.json`` for each case in
``_diff_golden.CASES``. The companion test ``test_regen_is_idempotent``
checks that running this script does not change any committed fixture.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Make src/ and tests/contract/ importable without relying on editable install.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "contract"))

from _diff_golden import CASES, build_case  # noqa: E402


def _write_case(case: str, golden_dir: Path) -> Path:
    target_dir = golden_dir / case
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "expected.json"
    with tempfile.TemporaryDirectory() as td:
        payload = build_case(case, Path(td))
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(text, encoding="utf-8")
    return target


def main() -> int:
    golden_dir = ROOT / "tests" / "golden" / "diff"
    for case in sorted(CASES):
        target = _write_case(case, golden_dir)
        print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
