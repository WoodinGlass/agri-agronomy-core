<h1 align="center">agri-agronomy-core</h1>

<p align="center"><strong>Offline, deterministic calculation engine and data contract for cultivation knowledge across countries and taxa.</strong><br>
Every number comes from a verified knowledge pack, never from a language model.</p>

<p align="center">
  <a href="https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml"><img src="https://github.com/WoodinGlass/agri-agronomy-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/status-pre--release-orange" alt="Status">
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License">
</p>

> **Pre-release.** Interfaces, the pack format and the JSON Schemas may change until `v0.1.0` is tagged. This project provides a calculation engine and a data contract; it is not professional agronomic advice. Read [Safety and limitations](#safety-and-limitations) before relying on any output.

## What this is

`agri-agronomy-core` is two things:

1. **A data contract.** JSON Schemas, a parameter dictionary, a pack format (CSV tables compiled into a verified SQLite pack) and a deterministic fact-resolution policy. The contract lives here. The data lives in [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge).
2. **A calculation engine.** Pure-Python functions that read a knowledge pack and compute climate indices, threshold checks, irrigation, fertilizer amounts, growing-media recipes, site suitability and propagation plans.

The engine covers vegetables, fruit, staple carbohydrates, fodder (grown for feed, not rations), ornamental plants and cultivated fungi. Rare species are carried as conservation attributes. "Agronomy" is used loosely to mean cultivation.

Adding a taxon or a country is a data change in `agri-knowledge`, not a code change here. Every number the engine returns comes from a pack with a citation.

It runs fully offline: no network access, database server, API key or GPU. The pack is a single immutable file; loading it never touches the network.

## What this is not

- **Not a data repository.** This repository contains the engine, the schemas, the dictionary and the sample pack used by tests. Real data lives in `agri-knowledge`.
- **Not a substitute for an agronomist, extension service, product label or local law.** It supports decisions; it does not make them.
- **Not a pesticide tool.** It never calculates pesticide, herbicide or fungicide doses. Such requests return `refer_to_label` or `refer_to_authority`.
- **Not a controller.** It does not operate pumps, valves, dosing units or any other actuator. It returns values and plans for systems that have their own safeguards.
- **Not a server, database or user interface.** There is no HTTP API or web editor, only a Python package and a command-line tool.
- **Not a sensor pipeline.** It does not read, clean or store sensor streams. Callers pass values in, with explicit units.
- **Not machine learning.** It contains no models and performs no training or inference.
- **Not a crop recommender, diagnostic tool or yield forecaster.** It evaluates the crop you name. It does not rank crops, identify pests or diseases, or predict yield.
- **Not a compliance tool.** It does not encode national or regional rules on fertilizers, water use or plant protection.
- **Not an encyclopedia.** Coverage is exactly what the pack contains, and `unknown` is a valid answer.

## Design principles

1. **Numbers come from data and tested code, never from a language model.** The engine may explain a result; it must not invent one.
2. **Refuse rather than guess.** Every calculation returns an `Outcome`. Missing input gives `insufficient_input`. Missing data gives `unknown`. An ambiguous taxon name gives `ambiguous`. A question that does not apply gives `not_applicable`. A legal or regulatory question gives `refer_to_authority`. There are no silent defaults, and expected "cannot answer" cases are never exceptions.
3. **The pack is the source of truth.** Every fact carries a `fact_id`, a status, an evidence grade, a scope and a source. Every `Result` records which fact IDs it used, the engine version, and the pack version and hash.
4. **Deterministic fact resolution.** The policy is fixed: filter by status ≥ the caller's minimum and by the license gate; match scope (empty key = wildcard, a filled key must cover the given context; a context not given is never considered a match); order by scope specificity, status, evidence, then `fact_id`. Conflicting equal-ranked facts raise a `FACT_CONFLICT` warning and are returned as alternatives. No matching fact gives `unknown`; the engine never borrows a value from another taxon or region.
5. **Pure and repeatable.** No I/O in calculators and no hidden clock: dates are arguments. The same input against the same pack always gives the same output.
6. **Immutable, explicit state.** A loaded pack is a `KnowledgeSet`: immutable, thread-safe, created by the caller. No singletons, hidden caches, current-directory lookups or environment-variable reads.
7. **Scoped, not global.** No single pH, temperature or dose fits every taxon, country and growing system. Values declare their scope; the engine answers `unknown` outside it.
8. **Conservative by default.** Fertilizer amounts have per-application caps, pesticides are never computed, conversions that need an explicit factor (such as EC to ppm) refuse to run without one, and safety-critical parameters are never `draft` or `imported`.
9. **Three kinds of change, three kinds of release.**
   - *Data only* (taxa, names, facts, countries, sources): a new pack release in `agri-knowledge`. No engine release.
   - *Dictionary* (core parameters used by calculators): an engine **minor** release. Extension parameters that are informational only are declared inside the pack and validated by the engine, with no engine release.
   - *Code* (a new calculation mode or archetype registered in the code): an engine release.

## Features

| # | Area | What it does | Target |
|---|------|--------------|--------|
| 1 | Data contract | JSON Schemas for `outcome`, `result`, `source`, `taxon`, `name`, `fact`, `hazard`, `parameter`, `dataset`, `manifest`. Core dictionary (`parameters.core.yaml`) with physical ranges, `applies_to`, tier requirements, phases per archetype, safety-class taxonomy and an append-only lock. | M1 |
| 2 | Pack lifecycle | `scaffold`, `build` (CSV → SQLite + manifest, reproducible), `load` (verify hash), `validate`, `diff`, `coverage`. | M1 |
| 3 | Registry | `resolve_taxon(name, country?, language?)` returns `ok`, `ambiguous` or `unknown`. `resolve_fact` applies the deterministic resolution policy. `meta()` reports engine version, pack version, `schema_version` and pack hash. | M1 |
| 4 | Climate | Vapor pressure deficit (VPD), growing degree days (GDD), daily light integral (DLI) and reference evapotranspiration (ET0: FAO-56 Penman–Monteith, with a Hargreaves–Samani fallback). Temperature estimate from elevation. | M2 |
| 5 | Thresholds and stages | Four-point trapezoid checks that return `optimal`, `suboptimal` or `critical`. Stage resolver from planting age and GDD; perennials driven by dated events supplied by the caller. | M2 |
| 6 | Irrigation, fertilizer, media and water | Three irrigation modes (`field_etc`, `paddy_awd`, `container_band`), nutrient-to-product conversion with safety caps, growing-media recipes and water-quality limits. Every mode declares the parameters it requires; missing → `unknown` or `insufficient_input`. | M3 |
| 7 | Suitability and propagation | Single and batch site suitability with `suitable`/`marginal`/`unsuitable` and per-factor reasons; dated propagation plans. | M4 |
| 8 | Exports | `tool_schemas.json` (function-calling schemas with `taxon_id`, `country`, `system`), `edge_thresholds.json` per site, `review_sheet.csv` per tier. | M5 |
| 9 | Command line | `validate`, `lint-sources`, `show`, `coverage`, `scaffold`, `build`, `diff`, `calc`, `export`. | M1+ |

## Quick start

### Install

Releases are distributed as git tags. Pin one:

```bash
pip install "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.0"
```

`v0.1.0` is not tagged yet. Until it is, replace `@v0.1.0` with `@main` in this and the Colab snippet, for development use only.

Requires Python 3.11 or newer (tested on 3.11, 3.12, 3.13 and 3.14, with a Windows smoke job). Runtime dependencies: Pydantic v2, jsonschema, PyYAML (`safe_load` only), pint, Typer and `sqlite3` (stdlib). Pure Python, CPU only.

### Google Colab

Open the quickstart notebook, or install in any Colab cell:

```python
!pip install -q "git+https://github.com/WoodinGlass/agri-agronomy-core@v0.1.0"
```

No API key or GPU is needed. The quickstart notebook is executed in CI, so it is verified to run.

### Python (preview)

```python
from pathlib import Path

from agri_core import registry
from agri_core.climate import vpd
from agri_core.pack import load_pack

# Load a pack explicitly. No current-directory lookup, no environment variables.
pack = load_pack(Path("/data/agri-knowledge/packs/2026.10"))

# Resolve a taxon by name. Returns ok, ambiguous or unknown.
taxon = registry.resolve_taxon("tomato", country="ID", pack=pack)
if taxon.status != "ok":
    print(taxon.status)                   # "ambiguous" or "unknown"

# Every result carries the fact IDs, engine version, pack version and hash.
r = vpd(temp_c=28.0, rh_pct=65.0)
if r.status == "ok":
    print(r.value, r.unit)                # about 1.32 kPa
    print(r.method, r.assumptions, r.warnings)
else:
    print(r.status)
```

### Command line

```bash
agri-core --help
agri-core validate --pack sample           # manifest + sources + facts
agri-core lint-sources --pack sample       # sources.csv checks
agri-core show --pack sample --taxon tomato
```

## Output contract

Every calculation returns an `Outcome`, a discriminated union whose `status` field says what happened. Expected "cannot answer" cases are outcomes, not exceptions, and every outcome is JSON-serializable. Exceptions are reserved for programmer errors, such as a wrong argument type or an unparseable unit string.

| `status` | Type | When |
|---|---|---|
| `ok` | `Result` | The calculation succeeded. |
| `insufficient_input` | `InsufficientInput` | A required input is missing, or a conversion needs an explicit factor (EC to ppm: 0.5, 0.64 or 0.7). Lists what is missing. |
| `unknown` | `Unknown` | The answer needs a value the pack marks as unknown, or no fact covers the requested scope. Gives a reason. |
| `not_applicable` | `NotApplicable` | The question does not apply (for example no standard Kc, or a propagation method the taxon does not use). Gives a reason. |
| `refer_to_label` | `ReferToLabel` | Pesticides: follow the product label and local regulations. |
| `ambiguous` | `Ambiguous` | A taxon name resolves to more than one candidate. Lists `candidates` (each with `taxon_id`, `name`, optional `note`); the caller must choose one. |
| `refer_to_authority` | `ReferToAuthority` | The answer depends on a legal or regulatory authority. Gives a `reason` and a sorted, unique list of `flags` (stable uppercase codes). |

A successful `Result` has `status` plus these payload fields:

| Field | Meaning |
|---|---|
| `status` | Always `ok`. |
| `value` | The computed value. Always finite: NaN and infinity are rejected because they are not valid JSON. |
| `unit` | Explicit unit. The library never guesses units. |
| `method` | How it was computed (for example which ET0 method). |
| `provenance` | Where the numbers came from: fact IDs, pack version, pack hash and source IDs. |
| `evidence` | Evidence grade(s) of the facts used. |
| `assumptions` | Every assumed or defaulted condition, stated explicitly. Each has a stable `code` and a message. |
| `warnings` | Fallback methods, out-of-range inputs, near-threshold results, `FACT_CONFLICT`. Each has a stable `code` and a message. |
| `capped` | `true` if a safety cap limited the result. |

The word `unknown` appears at three levels: a fact whose value is marked unknown (with a reason), a factor without data inside a suitability breakdown, and the `unknown` outcome returned when an answer would need such a value.

## Pack format

A pack is a directory with a manifest and CSV tables. `agri-core build` compiles it into a verified SQLite file plus a manifest that records hashes.

```
<pack>/
├─ advisories.csv         # critical corrections keyed by fact_id
├─ datasets.csv           # reference tables (fertilizer products, media, soil tests) with scope and license
├─ facts.csv              # one row per fact: fact_id, taxon_id, parameter, phase, value, scope, src, evidence, status
├─ hazards.csv            # hazard flags per taxon or scope
├─ names.csv              # aliases per taxon: taxon_id, name, language, kind
├─ pack.toml              # manifest: name, version, schema_version, engine_min
├─ sources.csv            # one row per source: id, url, license, commercial_use, access_date, citation
└─ taxa.csv               # one row per taxon: taxon_id, rank, scientific_name, parent_id
```

`pack.toml`:

```toml
name = "agri-knowledge"
version = "2026.10.0"
schema_version = 1
engine_min = "0.1.0"
```

### Facts

Each fact is one value at one scope. The engine resolves facts deterministically: filter, match scope, then order by specificity, status, evidence and `fact_id`. Conflicts between equally ranked facts raise a `FACT_CONFLICT` warning and are returned as alternatives. No matching fact gives `unknown`.

| Field | Meaning |
|---|---|
| `fact_id` | Stable identifier; never reused. Superseded facts are kept with `superseded_by`. |
| `taxon_id` | Opaque ID created by `agri-core scaffold`; scientific names may change without changing the ID. |
| `parameter` | A core parameter from `parameters.core.yaml` or an extension parameter declared in the pack. |
| `phase` | A phase from `phases_by_archetype`. |
| `value` | One of eight shapes: `trapezoid`, `range`, `scalar`, `enum`, `enum_set`, `bool`, `rule`, `unknown`. |
| `scope` | Country, region, elevation range, growing system, variety, season, use. Empty keys are wildcards; filled keys must cover the caller's context. |
| `src` | Source IDs, each defined in `sources.csv`. |
| `evidence` | `A` (guideline or peer-reviewed) to `D` (anecdotal). |
| `status` | `imported`, `draft`, `reviewed` or `approved`. Calculators only see facts at or above the caller's minimum. |

### Statuses and tiers

- **Statuses** move from `imported` (bulk import from a licensed dataset) to `draft` (entered, not yet checked) to `reviewed` (matched to its citation by a maintainer) to `approved` (signed off by a domain expert).
- **Tiers are derived, not declared.** `validate` and `coverage` compute:
  - **T0** identity only (name, rank, parent).
  - **T1** at least one `imported` fact.
  - **T2** every core parameter for the taxon's `use` / `archetype` is `reviewed` or `approved`, or explicitly unknown with a reason.
  - **T3** every core parameter is `approved`, and safety-critical parameters have been double-reviewed.

### Safety-critical parameters

Parameters with a `safety_class` other than `none` are safety-critical in the dictionary. The classes are:

| Class | Meaning |
|---|---|
| `dose_cap` | Functional upper bound on the recommendable amount per application. Prevents overdose without classifying the hazard type. |
| `toxicity_limit` | Threshold above which a hazard harms humans, animals or the environment. |
| `regulatory` | Flag or limit mandated by a specific jurisdiction. |

Safety-critical parameters may never be `draft` or `imported`; `approved` requires two independent reviews. Salinity (`soil_ec`, `water_ec_max`) is a tolerance condition for the plant, not an applied amount and not a hazard to humans, animals or the environment; it stays `safety_class: none`.

### Pack security

- The engine verifies the pack hash on load.
- SQLite is opened read-only and immutable, with `trusted_schema=OFF`.
- YAML, if used for overlays, is read with `safe_load` only.
- Pack size is bounded.
- A pack from an untrusted source is not loaded without a pinned hash.

## Dictionary

The core dictionary (`dictionary/parameters.core.yaml`) defines, for every parameter the engine consumes:

- `key`, `stage`, `shape` (one of the eight fact-value shapes), `unit`
- `physical_range` (physical sanity bound, not an agronomic judgement)
- `phase_set` (one of `none`, `biological`, `kc`) and optional `allowed_phases`
- `applies_to` (organism groups, archetypes, uses, systems, traits; AND between dimensions, OR within, omitted dimension means unlimited)
- `scope_keys` (which keys may appear in a fact's scope)
- `used_by` (which modules read the parameter) and `tier_required`
- `safety_class` and, when not `none`, a `rationale`
- `kind` (`core` or `extension`)
- `introduced_in` (SemVer of the dictionary release that first added the key)

The vocabulary files under `dictionary/vocab/` are the closed sets a pack may reference: `archetypes`, `phases_by_archetype`, `phase_sets`, `stages`, `systems`, `environments`, `uses`, `traits`, `organism_groups`, `climate_zones`, `growth_habits`, `establishment_states`, `yield_targets`, `scope_keys`, `modules` and `safety_classes`.

### Archetypes

Eight archetypes carry default biological phases: `annual`, `aquatic`, `biennial`, `epiphyte`, `fungal`, `geophyte`, `herbaceous_perennial`, `woody_perennial`.

Five more are present in the vocabulary without default phases and gain phases when a taxon and a calculator first need them: `algae`, `bryophyte`, `gymnosperm`, `lichen`, `pteridophyte`.

### Dictionary lock

- `dictionary/dictionary.lock` is an append-only log, one line per release: `<version> <contract_hash>`, sorted by SemVer. The last line is the running version.
- `contract_hash` is the SHA-256 of canonical JSON (sorted keys, no whitespace, `-0.0` normalized per RFC 8785) of `{parameters, vocab, units}`. The version string is not part of the hash; the `(version, hash)` pair is verified separately.
- `dictionary/history/<version>.json` is a frozen snapshot of `{version, parameters, vocab, units}` per release. Older snapshots are never edited; changing a released dictionary requires a new version and a new snapshot.
- `classify_change(old, new)` returns the required SemVer bump from a bundle diff. It is fail-closed: any change not explicitly classified as `PATCH` or a known `MINOR` pattern returns `MAJOR`. `MINOR` covers added keys and widened `applies_to` / `scope_keys` / `allowed_phases` / `physical_range` / vocabularies / custom units. `PATCH` is limited to `description` and `rationale` changes.

Adding a **core** parameter is a minor engine release. Adding an **extension** parameter is a pack change, validated by the engine, with no engine release.

## Taxa and identifiers

- Taxon IDs are created by `agri-core scaffold` and are opaque (Crockford base32 with a `T` prefix, ten characters). They are never reused.
- Scientific names may change without changing the ID.
- `rank` is one of `cultivar_group`, `genus`, `hybrid`, `species`.
- `parent_id` is for navigation only; it does not imply inheritance of facts. Values never flow from parent to child automatically.

## Repository layout

```
agri-agronomy-core/
├─ dictionary/
│  ├─ parameters.core.yaml   # 31 core parameters at dictionary_version 1.0.0
│  ├─ dictionary.lock        # append-only: <version> <contract_hash>, one line per release
│  ├─ history/               # frozen snapshots per release (1.0.0.json, ...)
│  ├─ unit_registry.yaml     # custom units (pH, ppm, percent, degree_day) + pint aliases
│  └─ vocab/                 # closed sets: archetypes, phases_by_archetype, phase_sets,
│                            #   stages, systems, environments, uses, traits, organism_groups,
│                            #   climate_zones, growth_habits, establishment_states,
│                            #   yield_targets, scope_keys, modules, safety_classes
├─ docs/                     # ADDING_A_TAXON, DICTIONARY, PACK_FORMAT, RESOLUTION_POLICY,
│                            #   REVIEW_GUIDE, SAFETY, ADR
├─ notebooks/                # Colab quickstart, executed in CI
├─ schema/                   # JSON Schemas: outcome, source, taxon, name, fact, hazard,
│                            #   parameter, dataset, manifest
├─ src/agri_core/
│  ├─ _samples/              # synthetic Apache-2.0 sample pack
│  ├─ climate/               # VPD, GDD, DLI, ET0
│  ├─ export/                # bundle, tool schemas, edge thresholds, review sheet
│  ├─ fertilizer/            # nutrient to product, unit conversion
│  ├─ irrigation/            # registry of modes: container_band, field_etc, paddy_awd
│  ├─ media/                 # media mixes and water quality
│  ├─ models/                # Outcome, Result, Dictionary, ParameterDef, PhaseSet, ScopeKey,
│  │                         #   row models, canonical JSON, ids, units
│  ├─ pack/                  # build, diff, license gate, load, migrate, scaffold, validate, verify
│  ├─ propagation/           # dated planner
│  ├─ registry/              # meta, resolve_fact, resolve_taxon
│  ├─ safety/                # dose caps, label referral
│  ├─ stages/                # stage resolver
│  ├─ suitability/           # scoring with reasons
│  ├─ thresholds/            # four-point trapezoid checks
│  ├─ cli.py
│  └─ py.typed
├─ tests/
│  ├─ contract/              # Outcome, dictionary, exported schemas stay stable
│  ├─ fixtures/              # synthetic data for behavior tests only
│  ├─ golden/                # validated against published examples or independent permissive implementations
│  ├─ offline/               # socket blocker proving no network access
│  ├─ perf/                  # performance budget checks
│  ├─ property/              # Hypothesis checks
│  ├─ scenario/              # end-to-end expectations
│  └─ unit/
├─ .github/                  # CODEOWNERS, workflows
├─ CHANGELOG.md
├─ LICENSE                   # Apache-2.0
├─ Makefile
└─ pyproject.toml
```

## Development

```bash
git clone https://github.com/WoodinGlass/agri-agronomy-core.git
cd agri-agronomy-core
pip install -e ".[dev]"
pre-commit install

ruff check . && ruff format --check .
mypy
pytest
agri-core validate --pack sample
agri-core lint-sources --pack sample
```

Tooling: pytest, Hypothesis, pytest-cov, ruff, mypy (strict), nbmake, nbstripout, pre-commit and pip-audit. A `socket`-blocking pytest plugin runs in every test to prove the engine is offline. A `windows-latest` smoke job runs alongside the Python 3.11–3.14 matrix on Ubuntu.

**Test kinds**

- `contract`: `Outcome`, dictionary, exported tool schemas and JSON Schemas stay stable.
- `golden`: results validated against published worked examples, or against independent permissively licensed implementations.
- `offline`: network access is blocked; any attempt to open a socket fails the test.
- `perf`: pack load and resolution stay within the published budget.
- `property`: Hypothesis checks such as unit round-trips, no negative amounts, and monotonic behavior with area.
- `scenario`: end-to-end expectations, for example a taxon whose every suitability factor is `unsuitable` in the requested scope must return `unsuitable`.
- `unit`: functions in isolation.

**Release gates (every release)**

- ruff and mypy (strict) are clean.
- Coverage is at least 90%, and 100% for `safety/`.
- CI is green on Python 3.11, 3.12, 3.13 and 3.14, plus the Windows smoke job; `pip-audit` runs in CI.
- Every test runs with network access blocked.
- The performance budget is met (see [Performance](#performance)).
- Notebooks execute (nbmake) and are committed without outputs (nbstripout).
- The pack and the wheel are reproducible: identical SHA-256 when built twice from the same inputs.
- `dictionary.lock` matches the running dictionary (`contract_hash` verified).
- `CHANGELOG.md` is updated.
- The GitHub Release contains the wheel, the sample pack, the built packs of `agri-knowledge` at the pinned version, and hashes.

## Performance

These targets are measured in CI and in Colab, and will be recalibrated once real pack sizes are known.

| Operation | Budget |
|---|---|
| Batch suitability, 5,000 taxa | ≤ 200 ms p95 |
| Load a pack with 10,000 taxa | ≤ 1 s |
| Peak memory | ≤ 200 MB |
| `resolve_taxon` p95 | ≤ 5 ms |

## Safety and limitations

- **Reference data, not advice.** Values may be incomplete, out of date, or wrong for your site, variety, climate, soil, water or growing system. Check with a local agronomist or extension service before acting.
- **Local rules and labels come first.** Rules on fertilizers, water use and plant protection differ between countries and regions. This library does not encode them.
- **Pesticides are out of scope.** Follow the product label and local regulations.
- **Caps are a backstop.** Per-application fertilizer caps are conservative upper bounds. They do not replace regional nutrient-management rules. Check the `capped` field.
- **Status matters.** Use `approved` facts for decisions affecting real crops. Use `reviewed` facts only in development and pilots with human oversight. Never use `draft` or `imported` facts for decisions.
- **Inputs decide quality.** The library checks types and units, but it cannot detect a faulty sensor or a wrong measurement.
- **No automatic actuation.** Do not connect outputs directly to pumps, valves or dosing units without independent interlocks (limits, timeouts, manual override) and human approval.
- **`unknown`, `not_applicable`, `ambiguous` and `unsuitable` are real answers.** Do not work around them.
- **No warranty.** See [License](#license).

## Data and provenance

The engine enforces provenance; the data lives in [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge).

- Every fact is an individual value (a number, a range or a rule) written in our own words and structure, with a citation.
- Passages, tables and figures are not copied from sources, and third-party datasets are not bulk-imported without a compatible license. Imports from open datasets (CC0, CC BY, public domain) happen only after the license gate.
- `sources.csv` has one row per source: ID, URL, license, `commercial_use`, access date and citation details.
- `commercial_use` is `yes`, `no` or `unclear`. It records what the source's own license permits, as read by a maintainer, and defaults to `unclear` for sources with no stated license. It is a convenience for filtering, not legal advice or a guarantee.
- `agri-core lint-sources` fails when `commercial_use` is `yes` but `license` names a non-commercial license (such as CC BY-NC). The license gate also rejects datasets whose license is ShareAlike (SA) or NoDerivatives (ND) when the pack would have to redistribute derived values.
- Golden tests use published numerical examples as test vectors, with citations. Where a published example is not openly licensed, an independent permissively licensed implementation is used instead. No text from a restricted source is copied.
- Reviewers are identified by ID; names appear only with consent. Packs and exports contain no personal data.
- Organizations and publications are named only to identify sources. There is no affiliation or endorsement.

## Contributing

Contributions are welcome. Data contributions go to [`agri-knowledge`](https://github.com/WoodinGlass/agri-knowledge); code contributions go here.

Data contributions (`agri-knowledge`):

- corrections to values, with a citation
- new facts with sources, evidence grades and an honest scope
- taxon aliases in other languages
- new taxa at any rank, with an honest `parent_id`

Code contributions (this repository):

- improvements to the pack loader, validator and diff
- new irrigation modes, calculation archetypes or parameter types, registered in the appropriate registry
- tests and golden vectors from published worked examples or independent permissively licensed implementations

Rules:

1. **Facts and citations only.** Do not paste text, tables or figures from sources, and do not bulk-import datasets. Pull requests that do will be declined.
2. **Every new fact needs** a `src` (added to `sources.csv` with URL, license, `commercial_use` and access date), an `evidence` grade, a `scope`, and a status. Imported facts start at `imported`; entered facts start at `draft`.
3. **Unknown stays unknown.** If no reliable source exists, write the fact with `unknown: true` and a reason.
4. **Everything is in English:** code, schema keys, identifiers and documentation. Local-language taxon names go in `names.csv`.
5. **Code changes need tests.** Changes under `safety/` also need 100% coverage, a maintainer review and, for safety-critical parameters, a second independent review.
6. **Licensing.** By submitting a contribution you confirm that you have the right to contribute it and that it is licensed under the same terms as the files it changes.

Domain experts can review through `review_sheet.csv` without a GitHub account, and the maintainer records the outcome. Code owners are listed in `.github/CODEOWNERS`.

## Security

- **Vulnerabilities** in code or dependencies: use GitHub's private vulnerability reporting (Security tab, then "Report a vulnerability") instead of a public issue.
- **Harmful data errors** (an unsafe cap, a wrong unit, a threshold off by an order of magnitude): report them to `agri-knowledge` with a citation and the `fact_id`. If you believe there is immediate risk, report it privately as above.
- The library makes no network calls. Pack loading verifies hashes and opens SQLite read-only with `trusted_schema=OFF`. YAML is read with `safe_load` only.

## Versioning and releases

- Semantic Versioning applies to the engine and to public contracts: `Outcome` and its members, the JSON Schemas, the dictionary and the exported tool schemas.
- Every pack carries a `schema_version` and an `engine_min`. The engine supports two consecutive `schema_version` values and ships `agri-core pack migrate` to move a pack forward. A pack that declares a `schema_version` the engine does not support is rejected; a pack that requires a newer engine than the one running is rejected.
- Every fact has a stable `fact_id`. A superseded fact is marked with `superseded_by`; a critical correction is published as an advisory in the pack.
- Every release pins the `agri-knowledge` version it was tested against, and a canary CI job runs against `agri-knowledge` `main` to surface incompatibilities early.
- `dictionary/dictionary.lock` records `<version> <contract_hash>` per dictionary release; the SemVer rule is that adding a key is `MINOR`, removing / renaming / changing shape, unit, phase_set, enum values or narrowing a dimension is `MAJOR`, and description / rationale changes are `PATCH`. `classify_change` enforces this and is exercised by the test suite.
- Releases are git tags and GitHub Releases (wheel, sample pack, built packs, hashes). They are not published on PyPI.

## Citing

If you use the engine in research or in a product, cite this repository with the release tag you used. If you rely on specific facts, also cite the original sources recorded in the pack's `sources.csv`.

## Milestones

| Milestone | Status | Scope | Done when |
|---|---|---|---|
| **M0** Foundation | Done | Repository, `pyproject.toml`, CI, pre-commit, `Outcome` and `Result` models, JSON Schemas, `sources.csv` linter, wheel smoke test. | CI is green on the empty but valid package, and a clean-venv install of the wheel passes `agri-core validate --pack sample`. |
| **M1** Data split | Done | Remove `profiles/` and `LICENSE-DATA`; the engine keeps schemas, dictionary and sample pack. | `pip install git+...` loads from a clean env without the `profiles/` folder; README reflects the split. |
| **M2** Contract models | Done | `Outcome` (7 statuses), `Result`, row models (`taxon`, `name`, `fact`, `hazard`, `dataset`, `source`), identifier primitives (Crockford base32), `ParameterDef` v1.0.0, `PhaseSet`, `ScopeKey`. | Drift tests, frozen / extra-forbid invariants, and identifier pattern tests pass. |
| **M3** Row JSON schemas | Done | JSON schemas for the 6 row models and the 8-shape `FactValue` union, generated from the Pydantic models. | Drift tests green; `EnumSetValue` in `FactValue` tested; `$defs` checked. |
| **M4** Core dictionary 1.0.0 | Done | 31 parameters at `dictionary_version: 1.0.0`, `dictionary.lock` (append-only), `history/1.0.0.json`, `classify_change` for SemVer, safety-class taxonomy. | Lock hash verified against the running dictionary; `introduced_in` matches first snapshot; `test_semver_compat` infrastructure ready. |
| **M5** Loader and sample pack | In progress | `compute_pack_hash` / `verify_pack_hash`; `load_knowledge_set(path)`; immutable `KnowledgeSet`; sample pack with 8 synthetic taxa (one per archetype, without real agronomic data). | Hash determinism and mismatch tests pass; sample pack loads cleanly; foreign keys on `taxon_id`, `parameter`, `src` verified. |
| **M6** Build | Not started | `scaffold` (opaque taxon IDs, never reused) plus `build` (CSV → SQLite + manifest, reproducible). | Wheel and pack build reproducibly (identical SHA-256 twice). |
| **M7** Validate, diff, coverage, license gate | Not started | Trapezoid order, scope validity, unit resolution, duplicate detection, tier derivation (T0–T3), `diff` report, `coverage`, license gate. | Sample pack passes validate with 0 errors; `diff` matches fixtures; coverage assigns tiers; license gate rejects NC + `commercial_use=yes`. |
| **M8** `resolve_taxon` and `resolve_fact` | Not started | Deterministic resolution per the fixed policy; `show` CLI. | `resolve_taxon` p95 ≤ 5 ms; resolution tests match fixtures. |
| **M9** Offline, performance, docs, tag `v0.1.0` | Not started | Socket-blocking pytest plugin, performance budget tests, `docs/` skeleton (`REVIEW_GUIDE`, `PACK_FORMAT`, `DICTIONARY`, `RESOLUTION_POLICY`, `SAFETY`, `ADDING_A_TAXON`). | Every test passes with network blocked; performance budget met; tag `v0.1.0`. |
| **M10** Climate, thresholds and stages | Not started | VPD, GDD, DLI, ET0 with fallback, temperature from elevation, threshold checks, stage resolver. | Golden tests pass; phases resolve per archetype; perennials use caller-supplied events. |
| **M11** Irrigation, fertilizer, media and water | Not started | Registry of irrigation modes (`container_band`, `field_etc`, `paddy_awd`), nutrient-to-product conversion with safety caps, growing-media recipes and water-quality limits. | `v0.1.0` passes against the sample pack and against `agri-knowledge` `v0.1.0`; irrigation results match scenario fixtures. |
| **M12** Suitability and propagation | Not started | Single and batch site suitability, per-factor reasons, hazard flags, dated propagation plans. | Batch mode within the performance budget; scenario tests including an `unsuitable` case. |
| **M13** Exports and documentation | Not started | `tool_schemas.json`, `edge_thresholds.json` per site, `review_sheet.csv` per tier, quickstart notebook, `docs/`. | A release tag includes exports, generated from the same Pydantic models as the library, with a stable contract test. |

## License

| Part | License | File |
|---|---|---|
| Code, tests, schemas, dictionary and documentation | Apache License 2.0 | `LICENSE` |
| Sample pack in `src/agri_core/_samples/sample_pack/` (synthetic data, no third-party facts) | Apache License 2.0 | `src/agri_core/_samples/sample_pack/` |
| Third-party sources cited by a pack | Their own licenses, which this project does not change | `<pack>/sources.csv` |

- **No third-party data in this repository.** The sample pack is synthetic. Real facts, including their licenses, live in `agri-knowledge` and each pack carries its own `sources.csv`.
- **Attribution.** When you redistribute a pack, credit the pack authors, link to the source repository, and indicate any changes you made. Each source keeps its own license; check it before commercial use.
- **No warranty.** The software and data are provided "as is", without warranties of any kind. To the maximum extent permitted by law, the authors and contributors are not liable for any loss or damage, including crop loss, arising from their use. The license text contains the binding terms.
- **No affiliation or endorsement.** Names of organizations, publications and datasets are used only to identify sources. This project is not affiliated with, endorsed by or sponsored by them. The license does not grant rights to any trademark.
- **Contributions** are licensed under the same terms (see [Contributing](#contributing)).
- **Dependencies** carry their own licenses.

Copyright 2026 WoodinGlass and the agri-agronomy-core contributors.
