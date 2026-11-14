# ADR-019: Native Rust kernel behind `agri_core._native`

- **Status:** Accepted (amended 2026-11-14)
- **Date:** 2026-11-13
- **Deciders:** WoodinGlass (maintainer)
- **Related:** ADR-001 (KnowledgeSet Protocol seam), ADR-002 (build and hash),
  ADR-003 (tiers and license), ADR-005 (license allowlist), ADR-009 (result
  envelope), ADR-010 (perf budgets)
- **Supersedes:** none
- **Superseded by:** none

## Context

The engine is pure Python and the current release (`v0.1.4`, M15) passes
2100 tests non-perf with ruff, ruff-format and mypy (strict) clean.

The measured performance on a Colab-class CPU is recorded in ADR-010 and
in the README. Concrete speed-up targets (for `pack build`,
`validate --strict`, `coverage`, `diff`, batch suitability) are **not**
fixed by this ADR. They will be set as an ADR-010 amendment **after**
profiling in M20 and M21, once the real cost split is known. This ADR
only commits to the architectural move and the gates that make the move
safe.

Two forces push the same way:

1. **Determinism across platforms.** Python's `json.dumps` and float
   `repr` are stable within a Python version but not guaranteed identical
   across platforms for all values. The pack hash (`content_hash`) and
   the dictionary hash (`contract_hash`) must be byte-identical on Linux,
   Windows and macOS.
2. **Performance.** Pack operations and batch resolution are the hot
   spots. Profiling (M20, follow-up) is expected to show fact resolution
   dominates batch suitability, not the math.

ADR-001 already isolates the loader behind a `Protocol`. That is the seam
this ADR uses: an implementation in another language can replace the
production path without changing the public API.

## Decision

Move a **small, explicitly bounded set** of behaviours to a native Rust
kernel. Everything else stays in Python.

### What moves to Rust

1. **Canonical JSON, SHA-256, `request_id`** (contract models, M2 surface
   today). One implementation of the hash, not two.
2. **Pack kernel** (M5-M7 surface today): `build`, `load`, `validate`,
   `diff`, `coverage` and tier derivation. SQLite is bundled with the
   wheel, so its version is pinned and does not follow the host OS.
3. **Taxon and fact resolution plus the name index** (M8 surface today),
   including name normalization. Python for single calls plus Rust for
   batch is a drift recipe, so one implementation only.
4. **`evaluate_trapezoid` and `batch_suitability`** (M13, M15 surface).
5. **M19 band math** (not yet started) is authored in Rust from day one,
   with an array-oriented API. NumPy is optional, never a required
   dependency.

### What stays in Python, deliberately

- **Public contract.** Pydantic `Outcome`, JSON Schema, dictionary, lock,
  `classify_change`, `tool_schemas.json`. Rust must not redefine any of
  these.
- **M11-M14 calculators plus `safety/`.** Already golden-tested and must
  be readable by agronomy reviewers. Port only if ADR-010 budgets fail.
- **M17 (soil water) and M18 (SPI, seasons).** Python first.
- **Propagation planner, `lint-catalog`, pint, Typer CLI, doc generators,
  notebooks, all tests.** Domain contributors stay productive in Python.

### Boundary

- The Rust kernel lives at `agri_core._native`. It is **not** a public
  API. Importing it directly is unsupported; the contract is the Python
  surface.
- One behaviour, one production implementation. After two clean releases
  of the Rust path, the old Python implementation moves to `tests/oracle/`
  and is used only for differential tests.

### Supply chain and safety

- `deny.toml` is default-deny, mirroring ADR-005. Allowed licenses: MIT,
  Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Zlib, Unicode-3.0.
  Rejected: any copyleft, any NonCommercial, no-license. Registry:
  crates.io only. Network crates are banned by name (`reqwest`, `hyper`,
  `tokio`), so "offline" becomes a dependency gate, not a promise.
- `#![forbid(unsafe_code)]` in `agri-kernel`. `unwrap()` and `expect()`
  are denied by clippy. `Cargo.lock` is committed. The SBOM includes the
  Rust crates.
- Determinism: no `HashMap` iteration on output; parallelism only across
  independent items, never inside a float reduction; transcendental
  functions via pure-Rust `libm`.
- Wheel is `cp311-abi3`: one wheel per OS and architecture, minimum
  Python 3.11, tested on 3.11, 3.12, 3.13 and 3.14. Platforms for
  `v0.1.6` (M20): **Linux x86_64, Windows x86_64, macOS arm64**, plus an
  sdist. No platform is deferred to a later milestone.
- `src/agri_core/_native.pyi` is checked with `mypy stubtest`.

### P2: honest RFC 8785 status, no breaking change in M20

The Python `canonical_json` in `src/agri_core/models/canonical.py` is
**not** fully RFC 8785-compliant. It applies only the `-0.0` to `0.0`
normalization that RFC 8785 requires. It uses Python's `json.dumps`
float representation (`1.0` becomes `"1.0"`, `1e-07` stays `"1e-07"`),
whereas RFC 8785 section 3.2.2.3 (ECMAScript) would produce `"1"` and
`"1e-7"`. On top of that, `content_hash` depends on `canonical_json`
(see `src/agri_core/pack/verify.py`, `_pack_toml_content`), so any change
to `canonical_json` changes every `content_hash`, including packs
already tagged `v0.1.0` through `v0.1.4`. Dictionary history already
contains 97 floats per version (1.2.0 and 1.2.1), so `contract_hash`
would also change for every released dictionary.

This ADR therefore pins the M20 contract as **byte-identical to the
current Python behavior**:

- Rust reproduces Python's output byte for byte, including float text
  (`1.0` is `"1.0"`, not `"1"`).
- `content_hash`, `contract_hash` and `request_id` are **unchanged** by
  M20. `artifact_sha256` may change (build backend moves to maturin) and
  is recorded in the CHANGELOG.
- The `canonical.py` docstring is corrected to state non-compliance with
  RFC 8785. This is a `description`-only change: `classify_change`
  returns `PATCH`.
- Migration to full RFC 8785 compliance is **out of scope** for M20 and
  is tracked as **ADR-020**. That ADR will define the new
  canonical form, add `dictionary` `v1.3.0` with a new `contract_hash`,
  re-tag packs, and set a migration window. It will be a breaking change
  and requires explicit approval.

The M21 acceptance gate keeps its meaning: `content_hash` of the sample
pack and of a 10k synthetic pack must be **identical** to the Python
result. If a Rust hash diverges, M21 is not done.

### Tag cadence

Sequential, no gaps, no `v0.2.x` until a real breaking change:

| Milestone | Tag |
|---|---|
| M16 Exports (Python, done first) | `v0.1.5` |
| M20 Rust foundation and M2 port | `v0.1.6` |
| M21 Pack kernel | `v0.1.7` |
| M22 Resolution and batch | `v0.1.8` |
| M17 Soil water balance | `v0.1.9` |
| M18 Drought and season indices | `v0.1.10` |
| M19 Vegetation-index band math | `v0.1.11` |
| M23 (conditional) Additional ports | `v0.1.12`+ |

PyPI publication is **not** tied to any of these tags. It begins only
when the whole repository is judged mature, with its own announcement in
`CHANGELOG.md`. Until then, releases are git tags and GitHub Releases
only, as they are today.

## Consequences

### Positive

- One implementation per behaviour removes a class of drift bugs.
- The hot paths can be measured, then targeted with evidence.
- Determinism is verified by a shared golden corpus, not assumed.
- The Python surface keeps its shape; contributors and reviewers are not
  forced into Rust.

### Negative

- Two toolchains in CI, and a release pipeline that must build and test
  wheels on three platforms (Linux x86_64, Windows x86_64, macOS arm64).
- The wheel gets larger (`rusqlite` is bundled).
- The team must maintain `deny.toml` and update it deliberately.
- The docstring correction surfaces a real gap: `canonical_json` is not
  RFC 8785 today. This is honest, but it is also a known limitation
  until ADR-020 lands.

### Neutral

- The public API is unchanged.
- Pack data is unchanged. `content_hash` is unchanged.
- Existing tests run unchanged. New tests are additive.

## Alternatives considered

1. **Rewrite the engine in Rust entirely.** Rejected: forces agronomy
   reviewers into Rust, breaks the "data, not code" split, and abandons
   a working, tested Python contract for no immediate gain.
2. **Keep Python only.** Rejected: does not move the hot paths and
   leaves platform determinism dependent on Python build details.
3. **Move canonical JSON only, keep pack kernel in Python.** Rejected:
   the pack kernel is the largest measured cost and cannot be improved
   inside Python without a native kernel.
4. **Fix RFC 8785 now (S).** Rejected: it is a breaking change for every
   published `content_hash` and `contract_hash`. Recorded as ADR-020.

## Notes

- The differential fuzz suite runs the Rust path against the Python
  oracle for at least one million cases before the Python path is moved
  to `tests/oracle/`.
- `Cargo.lock` is committed and `--locked` is used in CI.
- `maturin develop --release` is the dev loop. Users install wheels only;
  no Rust toolchain is required at install time.
- The license gate for crates (`cargo deny check`) runs on every PR and
  on every release.
- The following are explicitly **out of scope**: WASM, edge, device
  builds (see ADR-017), free-threaded Python 3.14t until there is demand,
  and any new Python dependency without its own ADR.


## Amendment 2026-11-14: tag order for M20 and M16

The original tag cadence placed M16 (Exports, Python) at `v0.1.5` and
M20 (Rust foundation) at `v0.1.6`. The maintainer chose to prioritise
the native foundation: M20 ships first, and M16 follows.

Revised tags (all other milestones unchanged):

| Milestone | Original tag | Revised tag |
|---|---|---|
| M20 Rust foundation and M2 port | `v0.1.6` | **`v0.1.5`** |
| M16 Exports (Python) | `v0.1.5` | **`v0.1.6`** |
| M21 Pack kernel | `v0.1.7` | `v0.1.7` |
| M22 Resolution and batch | `v0.1.8` | `v0.1.8` |
| M17, M18, M19 | `v0.1.9`-`v0.1.11` | `v0.1.9`-`v0.1.11` |
| M23 (conditional) | `v0.1.12`+ | `v0.1.12`+ |

Consequence acknowledged: K5 in `agri-knowledge` needs `review_sheet.csv`
from M16 and is therefore deferred by one tag. This is a deliberate
trade-off, not an oversight.

The P2 rule (M20 byte-identical with Python), the RFC 8785 migration
path (ADR-020, planned), the PyPI-last policy, and the "no `v0.2.x`
until a real breaking change" rule are unchanged.
