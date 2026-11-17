#!/usr/bin/env python3
"""Generate normalize vector goldens from the pinned Unicode oracle.

Requires a Python interpreter whose `unicodedata.unidata_version` matches
the ADR-019 §11.1 pin. Currently pinned to Unicode 16.0.0, e.g. Python
3.14. The script exits non-zero if the running interpreter's Unicode
version does not match `EXPECTED_UNICODE_VERSION`.

Deterministic: fixed codepoint sweep U+0041..U+2FA1D, no random seeds.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

EXPECTED_UNICODE_VERSION = "16.0.0"
SWEEP_START = 0x0041
SWEEP_END = 0x2FA1D

_REPO = Path(__file__).resolve().parents[1]
_VECTORS = _REPO / "tests" / "vectors"

# Import the reference Python normalizer. Prefer package import; fall back
# to standalone exec for environments where the package is not installed.
try:
    sys.path.insert(0, str(_REPO / "src"))
    from agri_core.pack.normalize import (  # type: ignore[import-not-found]
        normalize_name,
        normalize_scope_value,
    )
except ImportError:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "normalize_standalone",
        str(_REPO / "src" / "agri_core" / "pack" / "normalize.py"),
    )
    if _spec is None or _spec.loader is None:
        raise SystemExit("cannot load normalize.py") from None
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    normalize_name = _mod.normalize_name
    normalize_scope_value = _mod.normalize_scope_value


def _generate(fn, out_name: str) -> int:
    entries = []
    for cp in range(SWEEP_START, SWEEP_END + 1):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        ch = chr(cp)
        expected = fn(ch)
        if expected == ch:
            continue
        entries.append(
            {
                "cp": f"U+{cp:04X}",
                "input": ch,
                "expected": expected,
                "assigned_at_pin": unicodedata.category(ch) != "Cn",
            }
        )
    payload = {
        "version": unicodedata.unidata_version,
        "python": sys.version.split()[0],
        "entries": entries,
    }
    out = _VECTORS / out_name
    out.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(entries)} entries, unicode={payload['version']}")
    return len(entries)


def main() -> int:
    if unicodedata.unidata_version != EXPECTED_UNICODE_VERSION:
        print(
            f"ERROR: running interpreter Unicode {unicodedata.unidata_version} "
            f"!= expected {EXPECTED_UNICODE_VERSION}. "
            f"Install the pinned Python (ADR-019 §11.1) before regenerating.",
            file=sys.stderr,
        )
        return 1
    n_name = _generate(normalize_name, "normalize_name_16_0.json")
    n_scope = _generate(normalize_scope_value, "normalize_scope_value_16_0.json")
    print(f"OK: name={n_name}, scope={n_scope}, unicode={EXPECTED_UNICODE_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
