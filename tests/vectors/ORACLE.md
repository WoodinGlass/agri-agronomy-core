# RFC 8785 Oracle — Node.js `JSON.stringify`

## What this is

`tests/vectors/canonical_rfc8785.json` is generated from **Node.js
`JSON.stringify`** on **104** boundary-value inputs. Node implements
ECMA-262 §7.1.12.1 `Number.prototype.toString` exactly, which is the
number serialization form RFC 8785 §3.2.2.3 requires.

## Provenance

| | |
|---|---|
| Oracle | Node.js `JSON.stringify` |
| Version | `v22.23.4` |
| Binary | `/tools/node/bin/node` |
| Binary SHA-256 | `94efd062ed066c1a0b332e18249859c905e920eeada5df55d24c99b919629a90` |
| Date generated | 2026-11-15 |
| License | MIT (https://github.com/nodejs/node/blob/main/LICENSE) |

## Regenerate

    python scripts/gen_canonical_rfc8785.py

Requires `node` on PATH at the version above (or compatible).
The script is deterministic: fixed boundary lists, no random seeds.

## Normalization applied by the oracle script

The oracle script applies these transformations before calling
`JSON.stringify`:

1. **Object keys are sorted** by UTF-16 code-unit order (via
   `Object.keys(v).sort()`, which matches RFC 8785 section 3.2.3).
   Without this step, `JSON.stringify` emits insertion order and the
   vector would not be canonical.
2. **`-0.0` becomes `0`** (JSON spec has no negative zero).
3. **Whole floats become integers**: `1.0 -> 1`, `100.0 -> 100`,
   `1e16 -> 10000000000000000`. 12 of the 50 source floats fall under
   this rule. Non-whole floats keep their ECMAScript form
   (`1e-7 -> 1e-7`, `1e21 -> 1e+21`, `5e-324` for subnormal).

**Test implication**: iterating the 101 vector cases tests
`canonical_json_rfc8785(case["input"])` for the normalized input.
It does NOT test Python float `1.0` -> `b'{"v":1}'` — that case has
`input={"v": 1}` (int) in the vector. Float-specific cases are tested
explicitly in `tests/unit/test_canonical_rfc8785.py`.

## What we do **not** do

- Do not copy vectors from RFC 8785 Appendix B.
- Do not copy vectors from any standard document.
- All inputs are chosen by us (see `FLOATS` / `INTS` / `STRINGS` /
  `CONTAINERS` in `scripts/gen_canonical_rfc8785.py`).

This satisfies README §Data and provenance: "the output of an
independent, permissively licensed implementation whose name and
version are recorded next to the vectors".

## Two-implementation parity

`tests/unit/test_canonical_rfc8785.py` (Python) and
`crates/agri-kernel/tests/canonical_rfc8785_vectors.rs` (Rust, Phase B)
both read this file and must produce the exact `expected` bytes.
