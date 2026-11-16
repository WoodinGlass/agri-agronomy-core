# Unicode version pin (ADR-019 §11.1, §11.2)

Native normalization pins Unicode **14.0** for parity with the lowest
Python runtime in CI (`cp311` → 14.0). Behavior on codepoints assigned
after 14.0 is native-authoritative and recorded per Python version; the
parity contract requires bit-for-bit equality only on codepoints
assigned in 14.0.

## Crates (from `Cargo.lock`)

- `unicode-normalization =0.1.26` (NFKC) — allowlist: MIT/Apache-2.0
- `caseless =0.2.2` (C+F case folding) — allowlist: MIT
- ICU4X (`icu_casemap`, `icu_normalizer`) — dev-only, nightly; **not
  shipped**, license `Unicode-3.0` (allowlist)

## Python matrix (from `.github/workflows/ci.yml`)

| Python | Unicode |
|---|---|
| 3.11 | 14.0 |
| 3.12 | 15.0 |
| 3.13 | 15.1 |
| 3.14 | 16.0 |

## Oracle

Golden vectors generated with Python 3.14 / Unicode 16.0 (matches crate
pins). Tests for older runtimes skip codepoints that are `Cn` (unassigned)
in the running interpreter, so parity is asserted only on the intersection
of assignments across the matrix.

## Regenerate

    python scripts/gen_normalize_vectors.py

Requires Python 3.14 + `unicode-normalization`/`caseless` at the pinned
versions. Script is deterministic: fixed codepoint sweeps, no random
seeds.
