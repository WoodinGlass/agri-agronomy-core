# Fact value shape fixtures

One JSON file per shape in the ``FactValue`` union
(``agri_core.models.fact``). The filename stem equals the ``shape``
field inside the file.

## Why

1. **Oracle for the Rust migration (M21).** The native kernel must
   produce byte-identical canonical JSON for every shape. These
   fixtures are the minimal valid instance per shape.
2. **Guard against silent shape loss.** ``tests/unit/test_fact_value_shapes_coverage.py``
   derives the expected shape set from the ``FactValue`` union. Adding a
   shape without a fixture, or leaving an orphan fixture, fails the test.

## Why 8 when the sample pack has 6

``src/agri_core/_samples/sample_pack`` carries 6 of 8 shapes (per Q4
of the M16 review). ``bool`` and ``rule`` are not used by any core
parameter in ``dictionary/parameters.core.yaml`` today, so no sample
fact carries them. They remain ``extension-only`` and are validated
by this fixture set instead.

## Rules

- Every ``FactValue`` union member has exactly one fixture file here.
- The fixture is the minimal valid instance: no fields beyond what
  the model requires.
- Fixtures are committed. Do not auto-generate them: they are stable
  oracles for the Rust migration.
