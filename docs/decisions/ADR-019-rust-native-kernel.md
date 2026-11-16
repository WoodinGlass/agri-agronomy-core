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

## Amendment 2026-11-15: M21 preconditions

Prasyarat teknis yang dikunci sebelum M21 mulai. Semua angka berasal
dari spike 2026-11-15 di Colab.

**Spike results** (diverifikasi):
- `rusqlite` 0.42.0, `libsqlite3-sys` 0.40.0
- SQLite bundled 3.54.1 (`sqlite_version_number = 3054001`)
- `Connection::deserialize_read_exact(name, reader, size: usize, read_only: bool)` tersedia
- Hash-while-read wrapper: `sha256(expected) == sha256(from_wrapper)` pada 8192 byte round-trip
- `Connection: Send`, `Connection: !Sync`
- Round-trip 3/3 stabil

### 1. Kebijakan SQLite

- Bundled SQLite, bukan system. Fitur `bundled` di `rusqlite`.
- Minimum `sqlite_version_number >= 3054001` (SQLite 3.54.1), di-enforce via
  `test_sqlite_version_minimum` di `crates/agri-kernel/tests/` dan
  `tests/contract/test_sqlite_build.py`.
- `sqlite_version` dicatat di built `pack.toml` (informational, tidak di-hash).
- Pin crate per rilis; policy menetapkan minimum, Dependabot mengusulkan
  bump, maintainer memutuskan.

### 2. Kontrak parser

CSV dan TOML strictness adalah kontrak, bukan kebiasaan Python.
Lihat `docs/PACK_FORMAT.md` §CSV codec dan §TOML. Broken corpus di
`tests/fixtures/broken_{csv,toml}/` adalah KAT: setiap file punya
`expected_code` dan harus identik Python↔Rust.

### 3. Sunset fallback Python

Target rilis `v0.1.8` (M22). Setelah sunset:
- `src/agri_core/pack/*.py` yang diporting pindah ke `tests/oracle/`.
- Runtime tidak meng-import-nya.
- `meta().backends` mencatat backend aktif per-fungsi.

### 4. Perf gate relatif per phase

- B: `hash_pack_files` ≤ 0.5× Python di 10k pack.
- C: `build_pack` ≤ 0.5×.
- G: `load_knowledge_set` ≤ 0.5× + RSS ≤ 2× baseline + full perf suite
  (`resolve_fact` p95 ≤75 µs, `resolve_taxon` p95 ≤5 ms,
  `batch_suitability` 5k, multi-scale 100k).
- D/E/F: ≤ 0.5× masing-masing.
- Target aspirational: ≤0.2×. Diukur nightly di CI, artefak tersimpan.
- Gagal gate → fungsi tetap Python default, native di-gate per-fungsi
  via `meta().backends`.

### 5. Stop-loss berbasis kriteria

- Phase A: KAT RFC 8785 ≠ Node oracle **atau** Hypothesis divergence >0
  **atau** broken corpus mismatch → revert A2, tahan A1 default
  `pre-rfc8785`.
- Phase B/C/G/D/E/F: parity ≠ **atau** perf gate gagal **atau** RSS gate
  gagal → fungsi tetap Python default.
- Phase G spike: `deserialize_read_exact` tidak cocok → drop Rust `load`.
- Phase H: smoke 3 OS × 4 Python gagal → postpone tag.
- Prinsip: `v0.1.7` = subset M21 yang lulus gate. Tidak ada paksaan.

### 6. Clippy lints

`crates/agri-kernel/src/lib.rs` men-deny:
`unwrap_used`, `expect_used`, `panic`, `indexing_slicing`.

### 7. Backend per-fungsi

`meta().backends` = `dict[fn_name, "native" | "python"]`.
Bukan `meta().backend` tunggal.

### 8. Divergensi TOCTOU test

`test_stale_artifact` di-parametrisasi per backend:
- Python: raise `PACK_STALE_ARTIFACT` (perilaku lama).
- Native: immutable — ubah file setelah load → query tetap dari memori.
Divergensi didokumentasikan di sini sampai sunset (poin 3).

### 9. Phase B perf gate result (2026-11-15)

`hash_pack_files` native port: **perf gate did not pass**.

- Measured: **1.86× Python** on the 10k reference pack (10,007 files,
  68 MB, avg 6.8 KB/file), above the ≤0.5× gate (§4).
- Root cause: **SHA-256 implementation**. `rustcrypto sha2 0.11`
  delivers ~156 MB/s on the perf runner (Intel Xeon @ 2.20 GHz,
  `avx2` present, **no `sha_ni`**); OpenSSL `hashlib` delivers
  ~318 MB/s on the same CPU. Per-file SHA-256 alone is 435 ms
  native vs 214 ms Python.
- Secondary costs: per-file `format!` + hex encoding (~145 ms
  combined). PyO3 boundary copy measured at ~3 ms for 10k files
  (negligible).
- **Stop-loss applied (§5):** `meta().backends["hash_pack_files"]`
  reports `"python"` and the public wrapper uses pure Python. Native
  remains importable as `_native.hash_pack_files` for opt-in
  benchmarks.
- **Parity preserved as KAT:** 15 reference vectors, 10k synthetic
  pack, Hypothesis 1000-example fuzz, both `hash_alg` values. No
  user-visible KAT moves.
- **Follow-up (M21.5):** swap SHA-256 crate to `ring` (or equivalent
  OpenSSL-speed backend) and add `rayon` per-file parallelism.
  Expected to reach ≤0.5× on SHA-NI-enabled CPUs (CI nightly
  runners). Does not block tag `v0.1.7`.
- `tests/perf/test_hash_pack_files_perf.py` is `@pytest.mark.xfail(
  strict=False)` until the follow-up; XPASS signals the gate is met.

### 10. Phase D perf gate result — retroaktif (2026-11-16)

Ditulis retroaktif untuk melengkapi commit `d0610a1`
(`feat(native): C+D - Rust build_pack + validate_pack rules (M21) (#206)`,
merged 2026-11-16 +08:00), yang menyebut "Documented in ADR-019 §5, §10"
tetapi tidak menambahkan §10 ke ADR. Isi berikut adalah keputusan yang
**benar-benar diambil** pada commit tersebut — tidak ditulis ulang.

`build_sqlite_bytes` (Phase C) + 16 `validate` rules (Phase D) native
port: **perf gate did not pass**, stop-loss applied.

- **Parity preserved as KAT:** DDL SHA256 matches `468260bd...`; 16 rules
  produce identical `Finding` output (code/severity/message/location);
  sorted by Python `_sort_key` (file, line, key, taxon_id, code).
  121 Rust tests pass (99 existing + 22 new).
- **Why gate cannot pass on C+D alone:** 98% of `validate_pack` wall time
  is `load_knowledge_set_from_files` (structure check + Pydantic + CSV
  parse), which stays Python until Phase G. Porting 16 rules saves
  ~1.4s out of ~57s -> ratio ~1.0x.
- **Stop-loss applied (§5):**
  - `meta().backends["build_pack"] = "python"`
  - `meta().backends["validate_pack"] = "python"`
  - Native opt-in: `_native.build_sqlite_bytes`,
    `_native.validate_pack_findings`.
  - `tests/perf/test_validate_pack_native_perf.py` is
    `@pytest.mark.xfail(strict=False)`; will XPASS after Phase G.
- **`artifact_sha256`** documented: will change **once** when
  `build_pack` flips to native (SQLite header writer version differs from
  Python stdlib sqlite3). Current default (Python) -> no KAT change.
- **Follow-up (Phase G, loader port):** unlocks
  `backends["validate_pack"]="native"`. Does not block tag `v0.1.7`.

### 11. Phase G4: native `load_knowledge_set` + `normalize_name` + `name_index` (2026-11-16)

Port `_load_built_pack`, `normalize_name`, `normalize_scope_value`, and
`build_name_index` to Rust as **one backend unit** (binding rules below).
This supersedes the "NameIndex tetap di Python" deferral in the
2026-11-15 amendment.

The decision trades a larger single PR for one property: every code path
that resolves a taxon name goes through **one** normalizer and **one**
index builder, so `resolve_taxon` cannot see two different names as equal
(or unequal) depending on which Python interpreter happens to be running.

#### 11.1 Unicode version pin

The native normalizer is authoritative. `unicode-normalization 0.1.26`
ships Unicode **18.0.0** tables; `caseless 0.2.2` ships **16.0.0** tables.
Using both as-is would make NFKC (18.0) and casefold (16.0) operate on
different Unicode versions — codepoints assigned in 17.0/18.0 would pass
through NFKC but not get casefolded. That is a pipeline incoherence we do
**not** ship.

**Pin: Unicode 16.0.0.** NFKC and casefold both run against 16.0 tables.
- `unicode-normalization` tables above 16.0 are dead for any input
  we accept (strict mode rejects unassigned-at-16.0).
- `caseless` at 16.0 matches.
- Golden oracle: Python 3.14 (`unicodedata.unidata_version == "16.0.0"`).

Version pin is asserted by `test_unicode_version_pin` (checks
`caseless::UNICODE_VERSION == (16, 0, 0)` and
`unicode_normalization::UNICODE_VERSION >= (16, 0, 0)`; the >= allows
the normalization crate to ship later tables while we reject input that
would exercise them) and `test_cargo_lock_single_unicode_normalization`.

Native pin is exposed at runtime as `meta().unicode_version == "16.0.0"`.

#### 11.2 Parity contract — version-minimum

Cross-version divergence in NFKC/casefold is a **property of Unicode**, not
a bug we introduce. Per Unicode stability policy, `toCasefold∘toNFKC` is
stable for codepoints already encoded when they were assigned; only newly
assigned codepoints can differ.

**Contract:**

- **Codepoints assigned in Unicode 14.0 or earlier:** byte-for-byte
  parity with every Python version in the CI matrix (3.11/14.0,
  3.12/15.0, 3.13/15.1, 3.14/16.0). No exceptions.
- **Codepoints assigned in 14.1–16.0:** native is authoritative. Python
  older than the codepoint's assignment version may differ; tests are
  **version-aware** (skip codepoints whose `unicodedata.category == "Cn"`
  in the running interpreter).
- **Codepoints assigned after 16.0:** native rejects in strict mode
  (§11.4); warning in normal mode.

Golden vectors are generated from the **pinned** oracle (Python 3.14 /
Unicode 16.0), not from whichever Python happens to run the tests.

#### 11.3 Normalization pipeline (binding)

`normalize_name(s)` and `normalize_scope_value(s)` implement exactly:

1. **NFKC** (Unicode 16.0, via `unicode-normalization`).
2. **Full case folding** (Unicode 16.0, via `caseless` `C`+`F` mappings).
3. **Hybrid lift** (`normalize_name` only): `U+00D7` -> ASCII `x`.
   `normalize_scope_value` skips this step.
4. **Whitespace collapse** against an **explicit codepoint list** (§11.4),
   not a language predicate.

`Python str.split()` and Rust `char::is_whitespace()` agree on U+0009–U+000D,
U+0020, U+00A0, U+1680, U+2000–U+200A, U+2028, U+2029, U+202F, U+205F,
U+3000, and disagree on U+001C–U+001F (Python: whitespace; Rust: not).
The two backends agree by **whitelisting** the same list. Emitted whitespace
is ASCII space only.

#### 11.4 Whitespace + strict-mode codepoint lists

Two explicit codepoint sets are committed:

- `WHITESPACE`: the list above (verified identical against Python
  `str.isspace()` at the pin).
- `UNSTABLE_AT_PIN`: `Cn` (unassigned) ∪ noncharacters (`U+FDD0..U+FDEF`,
  `U+*FFFE`, `U+*FFFF`) ∪ private-use (`Co`) ∪ controls (`Cc`).
  `surrogates (Cs)` are excluded from `UNSTABLE_AT_PIN` only because a
  valid UTF-8 string cannot contain them; they are rejected upstream.

**Strict mode** (`agri-core validate --strict`, pack-load default):
reject codepoints in `UNSTABLE_AT_PIN`. **Normal mode**: warning, proceed.

Rejection is **stability-driven**, not novelty-driven: Tulu-Tigalari
(assigned in 16.0) is accepted because its NFKC/casefold behavior is frozen
at the pin. Codepoints assigned in 17.0/18.0 are rejected because the pin
cannot vouch for their behavior across future interpreters.

**200-character cap** is applied **before** normalization, identically in
both backends. Lone surrogates are rejected in Python before FFI; the
native normalizer is never called with a string Python would have rejected.

#### 11.5 Backend unit — `normalize` + `name_index`

`normalize` and `name_index` ship as **one backend unit**. Four
combinations are tested:

| load backend | normalization backend | `resolve_taxon` |
|---|---|---|
| Python | Python | baseline |
| Python | Rust | must equal baseline |
| Rust | Python | must equal baseline |
| Rust | Rust | must equal baseline |

`meta().backends` records `"normalize_name"`, `"build_name_index"`, and
`"load_knowledge_set"` individually. Any of the four combinations must
produce identical `resolve_taxon` output for every fixture and every
fuzz case.

**Index built at load from raw rows.** `RustKnowledgeSet::__init__` builds
the name index eagerly from `TaxonRow`/`NameRow` rows it already holds.
No stored index, no index derived from Python, no index tied to a
`KnowledgeSet` class in a way that survives a backend switch. This is the
precondition that makes stop-loss safe (§11.7): if we flip native -> Python,
the Python `SQLiteKnowledgeSet._build` rebuilds its index from the same raw
rows, with the same normalizer, so `resolve_taxon` cannot see a
half-native / half-Python state.

#### 11.6 Determinism

- No `HashMap` iteration in output paths. `BTreeMap` and `sort` only.
- `Ambiguous.candidates` sorted by `taxon_id` (already §8).
- No locale, no clock, no environment variable read. Two runs against the
  same pack produce identical output.
- Index sort order per bucket: `(taxon_id, matched_via, language, name)` —
  exactly the Python order.

#### 11.7 Fail taxonomy + stop-loss

When a test fails, classify:

1. **Port bug** (isolated, fixable). Time-box: 2 fix cycles. Then (3).
2. **Unicode version diff** (`Cn` in the pinned oracle, or divergence only
   on codepoints newly assigned in 14.1–16.0). Expected. Handled by
   version-aware tests (§11.2). Not a stop-loss.
3. **Semantic diff on codepoints <=14.0**, triaged with the ICU4X oracle
   (dev-only, `icu_casemap` + `icu_normalizer`, license Unicode-3.0).
   **Stop-loss applies:** `normalize_name`, `normalize_scope_value`, and
   `build_name_index` stay Python; `load_knowledge_set` stays native if it
   independently passes. `backends` reports the mix.

Stop-loss condition is **not** "one test failed". It is "an unresolvable
semantic diff on codepoints whose behavior the pin promises to be
stable." A single port bug is a bug to fix, not a reason to abandon the
port.

#### 11.8 Security

- `#![forbid(unsafe_code)]` in `agri-kernel`. PyO3 binding (`agri-py`)
  is the only place `unsafe` is allowed, and only for FFI.
- Clippy deny: `unwrap_used`, `expect_used`, `panic`, `indexing_slicing`.
- Size limits enforced before allocation: `DEFAULT_MAX_BYTES = 100 MiB`
  (pack), `MAX_FIELD_BYTES = 16 KiB`, `MAX_ROW_BYTES = 64 KiB` (CSV).
- Hash-while-read: the SHA-256 of `pack.sqlite` is computed **as it is
  streamed into** `deserialize_read_exact`. The bytes that are hashed are
  the bytes that are opened. No TOCTOU window between hash and query.
- SQLite opened with `query_only = ON`, `trusted_schema = OFF`.
- Zero reachable panic under `cargo-fuzz` (24h gate). PyO3 converts any
  Rust panic to `PanicException`; the gate proves no such panic is
  reachable from any public binding.

#### 11.9 Perf gate

The <=0.5x gate applies to **post-load query paths**, not just `__init__`:

- `load_knowledge_set(built)`: <=0.5x Python `SQLiteKnowledgeSet._build`.
- `resolve_taxon` p95: <=5 ms (ADR-010 budget, unchanged).
- `resolve_fact` p95: <=75 µs (ADR-010 budget, unchanged).
- 100k-taxa scale ratio: <= gate from ADR-010 "multi-scale scaling".
- `batch_suitability` 5k: <= baseline.

RSS is measured **in a subprocess** (`ru_maxrss` / `VmHWM`), not via
`tracemalloc` (which does not see Rust allocations). Native RSS <=2x the
Python baseline. Missing a bound here is a stop-loss for the load port
only; `normalize` + `name_index` remain independently judged.

#### 11.10 Error codes + parity contract

All errors use the stable `PackError.code` set (§8). `RustKnowledgeSet`
raises the same Python exception type that `SQLiteKnowledgeSet` raises for
the same condition. `test_stale_artifact` is **parametrized per backend**:

- Python: changing `pack.sqlite` after load raises `PACK_STALE_ARTIFACT`.
- Native: `pack.sqlite` is read once into memory; changing the file after
  load is a no-op. `RustKnowledgeSet` is **immutable by construction**.
  Divergence recorded here (mirrors §8).

`mypy --strict` and `mypy stubtest` pass with `RustKnowledgeSet` typed
against the `KnowledgeSet` Protocol.

#### 11.11 Why this ships

Wrong taxon = wrong fact = wrong advice. The cost of a name normalization
bug is a crop-level decision made on the wrong species. We accept a larger
G4 (4 sub-cells, 7–9 working days) in exchange for:

- Full parity contract (§11.2), not a sample.
- Single backend unit (§11.5), tested in all four combinations.
- Cross-version safety (§11.1 pin + §11.2 version-aware tests).
- Fail taxonomy that distinguishes port bug from stop-loss (§11.7).
- Third oracle (§11.7) when the first two disagree.

The plan places full parity above speed.

#### 11.13 D3 (Phase G extension): pin tripwire + ICU4X third oracle (2026-11-17)

Tripwire tests added (`crates/agri-kernel/tests/unicode_version_pin.rs`,
`crates/agri-kernel/tests/cargo_lock_single.rs`,
`tests/contract/test_unicode_version_pin.py`,
`tests/contract/test_cargo_lock_single_unicode_normalization.py`):

- `caseless::UNICODE_VERSION == (16, 0, 0)` — exact.
- `unicode_normalization::UNICODE_VERSION >= (16, 0)` — lower bound. At
  `0.1.26` it ships **18.0** tables. That is coherent with the pin:
  strict mode (§11.4) rejects codepoints unassigned-at-16.0, and per
  Unicode stability policy NFKC output for assigned codepoints is
  locked; input that would exercise the 17.0/18.0 tables never reaches
  NFKC.
- `Cargo.lock` holds exactly one `unicode-normalization`, one `caseless`,
  one `icu_casemap`, and one `icu_normalizer`.
- `icu_casemap` / `icu_normalizer` pinned exactly at `2.4.0`, dev-only.

**ICU4X third oracle.** `crates/agri-kernel/tests/normalize_icu4x_oracle.rs`
uses `icu_casemap::CaseMapper::new().fold_string(...)` and
`icu_normalizer::ComposingNormalizer::new_nfkc().normalize(...)` — both
backed by the crate's `compiled_data` feature (default in 2.4.0) — to
reproduce the native pipeline on representative inputs. The test is
`#[ignore]` and runs nightly via `.github/workflows/rust.yml` job
`icu4x-oracle`, not on PRs.

Failure of the ICU4X oracle is **monitored, not blocking**. A semantic
diff on codepoints assigned at <=16.0 is a candidate stop-loss under
§11.7 (would flip `normalize` + `name_index` to Python as one unit); a
diff on newly assigned codepoints is expected per §11.2 and handled by
the version-aware parity tests.

License: ICU4X is `Unicode-3.0`, in `deny.toml` allowlist.

#### 11.12 Phase G4-4: backend stop-loss (2026-11-16)

**Stop-loss applied.** G4-4 flipped `_NATIVE_LOAD` to `True` and measured
the native load path on the 10k reference pack:

| Metric | Budget (§11.9) | Measured | Verdict |
|---|---|---|---|
| `load_knowledge_set(built)` | <=1400 ms (ADR-010 user budget) | **5854 ms min** | **FAIL** |
| Native / Python ratio | <=0.50x | **5.54x** | **FAIL** |

`_NATIVE_LOAD` reverts to `False`. Python `SQLiteKnowledgeSet` remains the
default. The native `RustKnowledgeSet` implementation is complete and
byte-identical to Python on parity + error codes; it stays reachable via
`_NATIVE_LOAD=True` for benchmarks. The follow-up (M21.5 or M22) either
meets §11.9 or records permanent stop-loss.

**Root cause.** Rust loads eagerly into a full in-memory `RustKnowledgeSet`
(all rows materialized as `Vec<Row>` + `BTreeMap` indexes), whereas Python
`SQLiteKnowledgeSet` is lazy (rows decoded on demand from SQLite). For the
`load` operation the correctness contract only requires the artifact be
verified and opened — Python's lazy open is ~5x cheaper than Rust's eager
materialization on the 10k pack. Native `resolve_fact` / `resolve_taxon`
that would benefit from eager indexes have not been ported (M22).

**Parity gate.** `tests/contract/test_native_parity_load.py` passes on
parity (properties, iterators, lookups, per-taxon, ids_lock, names_index)
using the `python_loader` fixture to force `_NATIVE_LOAD=False` for the
baseline. Error codes are byte-identical via `load_built_pack_native`
through `PackError.code`. These are M21 gates (§11.10) and both pass.

**Scope of the four-way matrix (§11.5).** Unchanged: the matrix lands with
M22 (`resolve_taxon` / `resolve_fact` / `name_index` in Rust). Not part of
M21 G4-4.

**Stale-artifact divergence.** `SQLiteKnowledgeSet` re-checks the `.sqlite`
file on each `names_index` call and raises `PackStaleArtifactError` when
the artifact was tampered. `RustKnowledgeSet` is eager + in-memory and
never re-reads the file, so it does not raise. Asserted explicitly in
`tests/contract/test_stale_artifact.py` (backend-parametrized). Deliberate
consequence of eager loading (ADR-001); not a stop-loss trigger — the
trigger here is the load perf gate.

**Follow-up.** M21.5 or M22 must either (a) meet §11.9 (<=1400 ms and
<=0.5x on 10k) or (b) record permanent stop-loss here. Until then,
`meta().backends["load_knowledge_set"]` reports `"python"`.
