# Security Policy

This document describes how to report a vulnerability or a harmful data error, which versions are supported, and what the library guarantees at v0.1.0.

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (current) | :white_check_mark: |
| < 0.1 | :x: |

## Reporting


- **Vulnerabilities** in code or dependencies: use GitHub's private vulnerability reporting (Security tab, then "Report a vulnerability") instead of a public issue.
- **Harmful data errors** (an unsafe cap, a wrong unit, a threshold off by an order of magnitude): report them to `agri-knowledge` with a citation and the `fact_id`. If you believe there is immediate risk, report it privately as above.
- The library makes no network calls. Pack loading verifies hashes and opens SQLite read-only with `trusted_schema=OFF`. YAML is read with `safe_load` only.

## Scope

**In scope for security reports:**

- A code path that lets a malicious pack escape the hash verification, size limit, allowlist or read-only SQLite guarantees.
- A denial-of-service vector in the loader or resolver (unbounded memory, unbounded time) reachable from a pack the caller chose to load.
- A dependency CVE that affects a supported version.

**Out of scope for this repository (report to `agri-knowledge`):**

- Wrong numbers, missing citations, or a threshold off by an order of magnitude in a fact. These are data errors, not engine vulnerabilities; report them with a `fact_id`.
- A safety-critical parameter marked `approved` without the required two reviewer IDs. Report it with the `fact_id` and the `reviewed_by` list.

## Security guarantees at v0.1.0

- **No network calls.** The engine does not open sockets. The test suite enforces this with `pytest-socket` (`--disable-socket`) and a CI job that runs the CLI under `unshare -n`.
- **Hash-verified packs.** Source packs verify `content_hash`; built packs verify `artifact_sha256`. A mismatch fails closed with `PACK_HASH_MISMATCH`.
- **Bounded size.** Pack size is bounded by `max_bytes` (default configured in `agri_core.pack.files`); a pack that exceeds it fails with `PackTooLargeError`.
- **Read-only SQLite.** Built packs are opened with `mode=ro&immutable=1`, `PRAGMA query_only = ON`, and `PRAGMA trusted_schema = OFF`. A TOCTOU guard raises `PackStaleArtifactError` if the artifact changes after load.
- **YAML safety.** Any YAML is read with `yaml.safe_load`; no other YAML entry point exists.
- **No actuation.** The library returns values and plans. It does not operate pumps, valves, dosing units or any other actuator.
