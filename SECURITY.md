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


## Repository process controls

These controls protect the supply chain of the library itself
(releases and CI), separate from the runtime guarantees above.

| Control | State |
|---|---|
| Branch protection on `main` | required status checks (19), linear history off, force-push off, deletion off |
| Tag protection on `v*` | ruleset: deletion and non-fast-forward forbidden, update forbidden |
| Workflow default permissions | `read` (write must be opted in per workflow) |
| Third-party actions | pinned by 40-char commit SHA with the tag as a comment |
| Secret scanning + push protection | enabled |
| Dependabot alerts + automated security fixes | enabled |
| CodeQL | default setup (GitHub-hosted, `python`); alerts in the Security tab |
| Dependency review | runs on every pull request (`.github/workflows/dependency-review.yml`) |
| Release attestation | `actions/attest-build-provenance` on wheel, sdist, sample_pack.zip, SHA256SUMS |
| PyPI publishing | Trusted Publishing (OIDC) via `.github/workflows/publish.yml`; no static token in the repository |
| `CODEOWNERS` | lists sensitive paths (`.github/workflows/`, `dictionary/`, `schema/`, `safety/`, `release.yml`) |
| `require_code_owner_reviews` | **off while the project has one maintainer**. A single person cannot self-approve; enabling it would block every change to a sensitive path. Turn on when a second maintainer joins. |

`CODEOWNERS` maps sensitive paths to the current maintainer, so a
future GitHub App or co-maintainer can be added without changing
every workflow.

## Engine has no persistent state

The engine is pure: no database, no logger, no telemetry, no
network calls. It reads a pack, computes, and returns an `Outcome`.
An outcome's `subject` (ADR-009) and `request_id` identify what
was asked and tie the result back to its inputs, but the engine
does not record them anywhere. Any persistence — request logs,
per-run traces, ``run_id`` checkpoints — is the caller's
responsibility. The engine does not store location, identity, or
any user-supplied data. Data-protection obligations belong to the
application that calls the engine.

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

## Takedown requests

If you believe material in this repository or in an `agri-knowledge`
pack infringes your rights, contact **woodinglass@gmail.com** with:

- The specific material (file path or `fact_id`).
- The basis of your claim.
- Your preferred remediation (removal, correction, attribution).

We will acknowledge within 5 working days and aim to resolve or
escalate within 30 days. This is a maintenance commitment, not a legal
representation.
