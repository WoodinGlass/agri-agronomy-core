## Summary

## License / data policy checklist

- [ ] New `sources.csv` rows have `commercial_use=yes` and a license on
      the allowlist (see `docs/decisions/ADR-005-license-allowlist.md`).
- [ ] New `datasets.csv` rows have a license on the dataset allowlist
      (no `LicenseRef-PublicDomain` in 0.1.2).
- [ ] `LicenseRef-PublicDomain` source rows have a `citation` starting
      with `basis:`.
- [ ] No data copied from restricted databases (IUCN Red List, Species+,
      FAO-56 tables, similar). Vectors are derived independently or from
      a permissively licensed implementation (name and version recorded).
- [ ] Taxonomic exclusions cite CITES, Permen LHK 106/2018, or a
      documented lawful cultivation pathway. Maintainer decisions are
      recorded in `docs/design/`, never in `CHANGELOG.md`.

## Contribution rights

- [ ] I have the right to contribute this material, and I license it
      under the Apache License 2.0 (section 5).

## Test plan

- [ ] `pytest -m "not perf"` pass locally
- [ ] `agri-core validate --pack sample` exit 0
- [ ] `agri-core validate --pack sample --strict` exit 0
- [ ] `agri-core lint-sources --pack sample` exit 0
