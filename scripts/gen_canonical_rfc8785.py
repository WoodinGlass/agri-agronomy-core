#!/usr/bin/env python3
"""Regenerate tests/vectors/canonical_rfc8785.json from Node oracle.

Requires Node.js v22.23.4 (or compatible) on PATH.

Input cases are constructed deterministically from boundary value lists
(see FLOATS/INTS/STRINGS/CONTAINERS below). No random seeds.
Running twice on the same Node version produces identical output.

See tests/vectors/ORACLE.md for provenance.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tests" / "vectors" / "canonical_rfc8785.json"

# ------------------------------------------------------------------
# Deterministic boundary values (do not reorder; output depends on order)
#
# Node.js JSON.stringify applies ECMA-262 §7.1.12.1 normalization to the
# input before echoing it, which affects the vector file's `input` field:
#   - -0.0 → 0 (JSON spec has no negative zero)
#   - whole floats → integer: 1.0 → 1, 100.0 → 100, 1e16 → 10000000000000000
#   - non-whole floats preserved: 1.5, 1e-7 → 1e-7, 1e21 → 1e+21
#   - strings: control chars \uXXXX-escaped; non-ASCII preserved UTF-8
#
# The vector CANNOT test Python-side float-whole normalization via input
# comparison: the stored input is already the normalized value. Those
# cases are tested explicitly in tests/unit/test_canonical_rfc8785.py
# (12 source floats become int in vector, all tested separately).
# Vector cases DO test: int stays int, non-whole float stays float,
# string escaping rules match Node.
# ------------------------------------------------------------------

FLOATS = [
    # Basic
    0.0,
    -0.0,
    1.0,
    -1.0,
    1.5,
    -1.5,
    0.5,
    -0.5,
    2.5,
    -2.5,
    # Decimal precision
    0.1,
    0.2,
    0.3,
    0.7,
    0.9,
    1.1,
    1.2,
    1.3,
    1.7,
    1.9,
    # Small magnitudes (scientific threshold)
    1e-1,
    1e-2,
    1e-3,
    1e-4,
    1e-5,
    1e-6,
    1e-7,
    1e-10,
    1e-100,
    1e-300,
    # Large magnitudes
    1e1,
    1e2,
    1e3,
    1e6,
    1e10,
    1e15,
    1e16,
    1e20,
    1e21,
    1e22,
    # Subnormal and extremes
    5e-324,
    1e-308,
    1e-307,
    1.7976931348623157e308,
    # Precision edge (shortest round-trip)
    1.2345678901234567,
    # Irrationals (stable decimal repr)
    3.14159265358979,
    2.718281828459045,
    1.4142135623730951,
    # Min normal
    2.2250738585072014e-308,
    # Negative small
    -1e-7,
    # Even tiebreak (ECMA-262 s7.1.12.1: exact tie -> even last digit)
    70368744177664.125,  # 2^46 + 0.125; Rust {:e} -> .13, ECMA wants .12
    1125899906842624.2,  # 2^50 + 0.2
    -70368744177664.125,  # sign variant
]

INTS = [
    0,
    1,
    -1,
    42,
    -42,
    1000,
    -1000,
    2**31 - 1,
    -(2**31),
    2**31,
    2**53 - 1,
    -(2**53 - 1),
    2**53,
    -(2**53),
    123456789,
]

STRINGS = [
    "",
    "a",
    "hello",
    "abc123",
    "caf\u00e9",
    "\u65e5\u672c\u8a9e",
    "emoji \U0001f600",
    "\U0001f600",
    "\u0000",
    "\u0001",
    "\u001f",
    "\t",
    "\n",
    "\r",
    "\b",
    "\f",
    '"',
    "\\",
    "/",
    "with space",
    "with\nnewline",
]

CONTAINERS = [
    {},
    [],
    {"b": 1, "a": 2},
    {"z": 1, "m": 2, "a": 3},
    {"b": 2, "a": 1, "c": [3, 1, 2]},
    [1, 2, 3],
    ["a", "b", "c"],
    {"a": {"b": {"c": 1}}},
    {"arr": [1, 2, 3]},
    [True, False, None],
    {"bool": True, "null": None},
    {"nested": {"x": [1, 2, 3]}, "y": "v"},
    {"float": 1.5, "int": 42, "str": "x"},
    {"v": 1.0, "w": 1.5, "z": 0.0},
    [1.0, 2.0, 3.0],
]

NODE_SCRIPT = r"""
const fs = require("fs");

// RFC 8785 section 3.2.3: sort object keys by UTF-16 code units.
// Array.prototype.sort on string keys uses UTF-16 code unit order,
// matching the spec. Without this step, JSON.stringify emits insertion
// order and the vector would not be canonical.
function sortKeys(v) {
    if (Array.isArray(v)) return v.map(sortKeys);
    if (v !== null && typeof v === "object") {
        const sorted = {};
        for (const k of Object.keys(v).sort()) sorted[k] = sortKeys(v[k]);
        return sorted;
    }
    return v;
}

const data = JSON.parse(fs.readFileSync(0, "utf8"));
const out = data.map(({input}) => ({
    input,
    expected: JSON.stringify(sortKeys(input))
}));
process.stdout.write(JSON.stringify(out));
"""


def build_cases() -> list:
    """Build 100 cases: floats/ints/strings wrapped in {"v": ...} to
    preserve -0.0 through JSON serialization; containers as-is."""
    cases = []
    for f in FLOATS:
        cases.append({"v": f})
    for i in INTS:
        cases.append({"v": i})
    for s in STRINGS:
        cases.append({"v": s})
    for c in CONTAINERS:
        cases.append(c)
    return cases


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("error: node not found on PATH", file=sys.stderr)
        return 1
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"node: {node}  {version}")

    cases = build_cases()
    print(f"cases: {len(cases)}")
    assert len(cases) >= 100, f"need >=100 cases, got {len(cases)}"

    payload = [{"input": c} for c in cases]
    result = subprocess.run(
        [node, "-e", NODE_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"error: node failed: {result.stderr}", file=sys.stderr)
        return 1
    oracle = json.loads(result.stdout)
    assert len(oracle) == len(cases), f"count mismatch {len(oracle)} != {len(cases)}"

    OUT.write_text(json.dumps(oracle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote: {OUT}  ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
