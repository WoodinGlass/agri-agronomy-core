# Unicode version pin (ADR-019 §11.1, §11.2)

Native normalization pins Unicode **16.0.0** for both NFKC
(`unicode-normalization`) and casefold (`caseless`), matching the golden
oracle (Python 3.14 / `unicodedata.unidata_version == "16.0.0"`). Per
Unicode stability policy, `toCasefold ∘ toNFKC` is stable for codepoints
already assigned; only codepoints newly assigned in later versions can
diverge.

## Crates (from `Cargo.lock`)

- `unicode-normalization =0.1.26` (NFKC) — allowlist: MIT/Apache-2.0
- `caseless =0.2.2` (C+F case folding) — allowlist: MIT
- ICU4X (`icu_casemap`, `icu_normalizer`) — dev-only, nightly; **not
  shipped**, license `Unicode-3.0` (allowlist); D3 adds the third-oracle
  parity test

## Parity contract (ADR-019 §11.2)

- **Codepoints assigned in Unicode 14.0 or earlier:** byte-for-byte
  parity with every Python version in the CI matrix (3.11/14.0,
  3.12/15.0, 3.13/15.1, 3.14/16.0).
- **Codepoints assigned in 14.1–16.0:** native is authoritative; Python
  older than the codepoint's assignment version may differ. Tests are
  version-aware: skip codepoints whose `unicodedata.category(chr(cp)) ==
  "Cn"` in the running interpreter.
- **Codepoints assigned after 16.0:** native rejects in strict mode
  (ADR §11.4); warning in normal mode.

## Python matrix (from `.github/workflows/ci.yml`)

| Python | Unicode |
|---|---|
| 3.11 | 14.0 |
| 3.12 | 15.0 |
| 3.13 | 15.1 |
| 3.14 | 16.0 |

## Golden vectors

Golden files are generated from the pinned oracle (Python 3.14 /
Unicode 16.0), not from whichever Python happens to run the tests:

- `normalize_name_16_0.json`
- `normalize_scope_value_16_0.json`

The `*_15_1.json` files (from Python 3.13.18 / Unicode 15.1.0) are
retained as historical reference but are **not** used by parity tests.

## Tests

- `tests/contract/test_native_parity_normalize.py` — for every entry in
  the 16.0.0 golden:
  - **Native** matches `expected` unconditionally (native is
    authoritative).
  - **Python** matches `expected` only when the codepoint is assigned
    in the running interpreter's Unicode version; unassigned codepoints
    (`unicodedata.category(chr(cp)) == "Cn"`) are skipped per Unicode
    stability policy.

## Regenerate

    python scripts/gen_normalize_vectors.py

Requires Python whose `unicodedata.unidata_version` matches the
ADR-019 §11.1 pin (currently **16.0.0**, e.g. Python 3.14). The script
is deterministic: fixed codepoint sweep U+0041..U+2FA1D, no random
seeds.
