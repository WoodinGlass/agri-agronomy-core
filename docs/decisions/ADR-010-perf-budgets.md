# ADR-010: CLI performance budgets for `build`, `validate`, `coverage`, `diff`

## Status

Proposed 2026-11-04.

## Context

The perf suite covers pack loading (`load_knowledge_set`), peak
memory, `resolve_taxon`, and coverage scaling. It does **not** cover
the four main CLI operations on a 10k-taxa pack. Those are what the
release workflow and users actually run, so a slow `build` in CI is
a release risk even when the in-process algorithms are fast.

A first measurement round surfaced a real O(n^2) bug in
`derive_tier`: `derive_all_tiers` re-scanned every fact per taxon.
That bug was fixed in #131 -- `derive_tier` now uses
`KnowledgeSet.facts_for(taxon_id)`, backed by the pre-built
`_facts_by_taxon` index. Coverage on 10k taxa now completes in
**684 ms** in-process (`derive_all_tiers` only), so a CLI-level
budget is meaningful.

## Decision

Add four CLI perf gates. Each spawns `agri-core <cmd>` once on a
10k-taxa / 320k-fact synthetic pack and asserts wall time.

| Command | Target | Budget |
|---|---|---|
| `agri-core pack build` | 10k source -> out | 160 s |
| `agri-core validate --strict` | 10k **source** | 90 s |
| `agri-core coverage --json` | 10k **built** | 27 s |
| `agri-core diff --json` | 10k built <-> built | 48 s |

Budgets are **min-of-2/3 in Colab x 1.5**, rounded to the nearest
1000 ms. CI runners are typically 2-4x faster than the throttled
Colab CPU these were measured on, so effective CI headroom is
3-6x. The margin is chosen to catch catastrophic regressions (>= 3x),
not 20% drift.

### What these tests measure

- **Wall time of a subprocess.** Each test spawns `agri-core <cmd>`
  and measures with `time.perf_counter()`. This includes process
  startup, Python imports, and pack I/O.
- **CLI behavior at scale.** Smoke tests at the boundary users and
  the release workflow touch.

### What these tests do not measure

- **Per-function algorithm cost.** For that, see
  `test_built_load_budget` (in-process, tight budget on
  `load_knowledge_set`) and `test_coverage_scaling` (in-process
  scaling ratio for `derive_all_tiers`).
- **Cold-start optimization.** Startup cost is real but out of
  scope; a follow-up may add a `--no-validate` flag to `pack build`
  for CI-only runs.

### Why `--json` for coverage and diff

Coverage text output echoes one line per taxon (10k lines), which
dominates wall time via pipe I/O (measured ~1 s overhead on 10k
taxa). `--json` emits a single blob. Both are functionally identical
for the underlying work; `--json` makes the measurement reflect
compute, not I/O.

### Why `validate` targets the source pack

`agri-core validate` expects source CSVs (`taxa.csv`, `facts/*.csv`,
etc.). A built pack contains `pack.sqlite` only and `validate`
rejects it by design (`PACK_INVALID: required file missing:
taxa.csv`). The 47 s budget covers the source tree, not the SQLite
artifact. Built-pack load correctness is covered by
`test_built_load_budget`.

## Consequences

- CI's `Performance budget` job grows by ~2-3 minutes.
- A 3x or worse regression in any of the four CLI operations
  fails the build.
- The 1.5x Colab margin will be **tightened** once 2 weeks of CI
  data has accumulated, using real CI medians instead of a Colab
  estimate. That is a follow-up PR.

## Follow-up

- Tighten budgets after 2 weeks of CI data.
- If `build` startup dominates while the algorithm is fast, consider
  splitting `pack build` into validate-only and write-only phases for
  CI (separate decision).
- Revisit if `agri-knowledge` pack sizes grow beyond 10k taxa /
  320k facts (the reference workload in README §Performance, M15).


## Amendment 2026-11-11 (M15)

M15 added 12 suitability and propagation parameters to the dictionary
(v1.2.0), taking the reference workload from 200k to 320k facts
(10k taxa x 32 `phase_set=none` params). Five budgets were rebaselined
from measurements on the same Colab-class CPU:

| Test | Before | After | M15 actual |
|---|---|---|---|
| `test_build_budget` | 135 s | 160 s | 128.2 s |
| `test_validate_budget` | 70 s | 90 s | 71.4 s |
| `test_diff_budget` | 36 s | 48 s | 36.9 s |
| `test_built_load_budget` | 1000 ms | 1400 ms | 1116 ms |
| `test_source_load_canary` | 40 s | 90 s | 67.4 s |

`test_coverage_budget` (27 s vs 24.5 s measured) and
`test_built_load_peak_memory` (200 MB vs 61.8 MB measured) still
pass with headroom and are unchanged.

### In-process batch suitability (M15, measure only)

M15 ships `test_suitability_perf.py` to measure `batch_suitability` on
5,000 taxa in-process (not via subprocess). Per Q7 (M15): measure, do
not claim a p95 budget yet.

| Test | Aspirational target | Current gate | M15 actual (Colab, 3-run) |
|---|---|---|---|
| `test_batch_5000_actual` | 200 ms p95 (from M9 planning) | catastrophic only (`< 5000 ms`) | min 2266 / median 2886 / max 4347 ms |

The 200 ms target was set at M9 when suitability was spec'd as a tight
batch gate. Actual M15 is ~14x that number on a Colab-class CPU.
Tightening is a follow-up (M16+), once a CI baseline exists. The
current test prints min/median/max and asserts only that the best run
is under 5,000 ms (~1.7x the observed median), so it catches
catastrophic regressions without failing on Colab throttling.

## References

- ADR-003 (tiers, license, duplicates) -- `derive_all_tiers` backs
  `coverage`
- PR #131 -- `derive_tier` O(n^2) -> O(n) fix
- `README.md` §Performance
- `tests/perf/conftest.py` -- session-scoped `perf_pack` fixture
- `tests/perf/_gen_pack.py` -- shared 10k-pack generator
