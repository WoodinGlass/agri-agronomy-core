"""agri-core command line."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from agri_core import __version__
from agri_core.models.fact import FactRow, format_value
from agri_core.models.finding import Finding, FindingSeverity
from agri_core.models.refusals import Ambiguous
from agri_core.pack import (
    KnowledgeSet,
    PackError,
    PackManifest,
    Tier,
    compute_pack_hash,
    derive_all_tiers,
    diff_packs,
    hash_pack_files,
    load_knowledge_set,
    parse_manifest_bytes,
    read_pack_bytes,
)
from agri_core.pack.build import build_pack, render_source_manifest
from agri_core.pack.loader import _default_dictionary
from agri_core.pack.scaffold import scaffold_taxon
from agri_core.pack.validate import validate_pack, validate_pack_report
from agri_core.registry import TaxonOk, lint_csv_text, resolve_taxon

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PACK = 3
EXIT_UNEXPECTED = 70

app = typer.Typer(
    name="agri-core",
    help="Offline, deterministic crop profiles and agronomy calculators.",
    no_args_is_help=True,
    add_completion=False,
)

pack_app = typer.Typer(
    name="pack",
    help="Pack maintenance commands.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(pack_app, name="pack")


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"agri-core {__version__}")
        raise typer.Exit(EXIT_OK)


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """agri-core command line."""


def _resolve_pack_path(spec: str) -> Path:
    if spec == "sample":
        from importlib.resources import files as _files

        return Path(str(_files("agri_core") / "_samples" / "sample_pack"))
    return Path(spec)


def _load_and_print(
    spec: str, *, print_pack_line: bool = True
) -> tuple[Mapping[str, bytes], PackManifest]:
    path = _resolve_pack_path(spec)
    try:
        files = read_pack_bytes(path)
        manifest = parse_manifest_bytes(files["pack.toml"])
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    if print_pack_line:
        kind = "sample" if spec == "sample" else str(path.resolve())
        typer.echo(f"pack: {manifest.name} {manifest.version} ({kind})")
    if manifest.synthetic:
        typer.echo("SYNTHETIC DATA", err=True)
    return files, manifest


def _emit_findings(findings: list[Finding]) -> tuple[int, int]:
    errors = 0
    warnings = 0
    for f in findings:
        file = f.location.file or "<unknown>"
        line = f.location.line
        loc = f"{file}:{line}" if line else file
        typer.echo(f"{f.severity.value}: {f.code} {loc}: {f.message}")
        if f.severity == FindingSeverity.ERROR:
            errors += 1
        elif f.severity == FindingSeverity.WARNING:
            warnings += 1
    return errors, warnings


def _compute_exit_code(errors: int, warnings: int, *, strict: bool) -> int:
    """Return the exit code for the validate command.

    Errors always exit 1. ``--strict`` promotes warnings to 1.
    No findings -> 0.
    """
    if errors > 0:
        return EXIT_ERROR
    if strict and warnings > 0:
        return EXIT_ERROR
    return EXIT_OK


def _count_commercial_use(sources_bytes: bytes) -> dict[str, int]:
    counts = {"yes": 0, "no": 0, "unclear": 0}
    text = sources_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if not row or not any(v for v in row.values() if v):
            continue
        cu = (row.get("commercial_use") or "").strip().lower()
        if cu in counts:
            counts[cu] += 1
    return counts


def _warn_if_unverified(manifest: PackManifest) -> None:
    if manifest.content_hash is None:
        typer.echo(
            "warning: PACK_UNVERIFIED: no manifest content_hash and no "
            "expected_hash; content not verified",
            err=True,
        )


@app.command(name="lint-sources")
def lint_sources(
    pack: Annotated[
        str,
        typer.Option("--pack", help="Path to a pack directory, or 'sample'."),
    ],
) -> None:
    """Check a pack's sources.csv for schema and consistency errors."""
    files, manifest = _load_and_print(pack)
    _warn_if_unverified(manifest)
    text = files["sources.csv"].decode("utf-8-sig")
    findings = lint_csv_text(text, today=date.today(), filename="sources.csv")
    errors, warnings = _emit_findings(findings)
    counts = _count_commercial_use(files["sources.csv"])
    typer.echo(
        f"sources: {sum(counts.values())} "
        f"(yes: {counts['yes']}, no: {counts['no']}, unclear: {counts['unclear']})"
    )
    typer.echo(f"errors: {errors}, warnings: {warnings}")
    if errors:
        raise typer.Exit(EXIT_ERROR)


@app.command(name="validate")
def validate(
    pack: Annotated[
        str,
        typer.Option("--pack", help="Path to a pack directory, or 'sample'."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of text."),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit 1 if any finding (errors or warnings) is present.",
        ),
    ] = False,
) -> None:
    """Validate a pack: manifest, sources, and structural integrity.

    Inspection only; always accepts synthetic packs. The SYNTHETIC DATA
    banner on stderr is the warning. Only calculation commands (M8+)
    require an explicit opt-in for synthetic data.

    ``--strict`` promotes warnings to exit 1 (errors are always exit 1).
    ``--json`` emits a structured report; the exit code is unchanged.
    """
    files, manifest = _load_and_print(pack, print_pack_line=not json_output)
    _warn_if_unverified(manifest)

    text = files["sources.csv"].decode("utf-8-sig")
    src_findings = lint_csv_text(text, today=date.today(), filename="sources.csv")
    counts = _count_commercial_use(files["sources.csv"])

    report, ks = validate_pack_report(files, allow_synthetic=True)

    # Load errors (report.findings from _report_from_error/_report_from_missing_key)
    # mean the pack could not be loaded. Exit 3, distinct from rule findings.
    if ks is None:
        for f in report.findings:
            loc_parts = []
            if f.location.file:
                loc = f.location.file
                if f.location.line:
                    loc = f"{loc}:{f.location.line}"
                loc_parts.append(loc)
            loc_str = " ".join(loc_parts) if loc_parts else "-"
            typer.echo(f"{f.severity.value}: {f.code} {loc_str}: {f.message}", err=True)
        raise typer.Exit(EXIT_PACK)

    combined = list(src_findings) + list(report.findings)
    combined.sort(key=lambda f: (f.location.file or "", f.location.line or 0, f.code))

    errors = sum(1 for f in combined if f.severity == FindingSeverity.ERROR)
    warnings = sum(1 for f in combined if f.severity == FindingSeverity.WARNING)

    if json_output:
        payload = {
            "pack": {
                "name": manifest.name,
                "version": manifest.version,
                "synthetic": manifest.synthetic,
                "verified": manifest.content_hash is not None,
            },
            "sources": {
                "total": sum(counts.values()),
                "yes": counts["yes"],
                "no": counts["no"],
                "unclear": counts["unclear"],
            },
            "report": {
                "report_version": report.report_version,
                "ok": errors == 0,
                "findings": [f.model_dump(mode="json") for f in combined],
            },
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _emit_findings(combined)
        typer.echo(
            f"sources: {sum(counts.values())} "
            f"(yes: {counts['yes']}, no: {counts['no']}, unclear: {counts['unclear']})"
        )
        typer.echo(f"errors: {errors}, warnings: {warnings}")

    exit_code = _compute_exit_code(errors, warnings, strict=strict)
    if exit_code != EXIT_OK:
        raise typer.Exit(exit_code)


@pack_app.command(name="lock")
def pack_lock(
    pack: Annotated[
        str,
        typer.Option(
            "--pack",
            help="Path to a pack directory (explicit path only; 'sample' is rejected).",
        ),
    ],
) -> None:
    """Rewrite pack.toml with the correct content_hash (comments not preserved)."""
    if pack == "sample":
        typer.echo(
            "error: pack lock requires an explicit path; 'sample' is not "
            "allowed. Pass the path, e.g. src/agri_core/_samples/sample_pack.",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)

    path = Path(pack)
    try:
        files = read_pack_bytes(path)
        manifest = parse_manifest_bytes(files["pack.toml"])
        validate_pack(files, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    # Compute the hash from the content we are about to write, not from the
    # current pack.toml (which may lack fields such as `synthetic` that
    # render_source_manifest normalizes in).
    content_without_hash = render_source_manifest(manifest, "")
    files_with_new_toml = dict(files)
    files_with_new_toml["pack.toml"] = content_without_hash
    new_hash = hash_pack_files(files_with_new_toml)
    content = render_source_manifest(manifest, new_hash)

    target = path / "pack.toml"
    tmp = path / "pack.toml.tmp"
    try:
        tmp.write_bytes(content)
        os.replace(tmp, target)
    except OSError as exc:
        typer.echo(f"error: OSError: {exc}", err=True)
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise typer.Exit(EXIT_UNEXPECTED) from exc

    verify_hash = compute_pack_hash(path)
    if verify_hash != new_hash:
        typer.echo(
            f"error: post-write hash mismatch: expected {new_hash}, got {verify_hash}",
            err=True,
        )
        raise typer.Exit(EXIT_UNEXPECTED)

    typer.echo(f"wrote content_hash = {new_hash}")


def _reject_existing_artifacts(out_dir: Path) -> None:
    for name in ("pack.sqlite", "pack.toml"):
        target = out_dir / name
        if target.exists():
            typer.echo(
                f"error: {target} already exists; remove it or choose another --out",
                err=True,
            )
            raise typer.Exit(EXIT_USAGE)


@pack_app.command(name="build")
def pack_build(
    pack: Annotated[
        str,
        typer.Option(
            "--pack",
            help=("Path to a source pack directory (explicit path only; 'sample' is rejected)."),
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output directory for pack.sqlite and pack.toml."),
    ],
    update_source_hash: Annotated[
        bool,
        typer.Option(
            "--update-source-hash",
            help="Rewrite source pack.toml when content_hash or formatting is stale.",
        ),
    ] = False,
) -> None:
    """Validate a source pack and write a built (SQLite) pack."""
    if pack == "sample":
        typer.echo(
            "error: pack build requires an explicit path; 'sample' is not "
            "allowed. Pass the path, e.g. src/agri_core/_samples/sample_pack.",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)

    out_dir = Path(out)
    _reject_existing_artifacts(out_dir)

    try:
        result = build_pack(Path(pack), out_dir, update_source_hash=update_source_hash)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc
    except OSError as exc:
        typer.echo(f"error: OSError: {exc}", err=True)
        raise typer.Exit(EXIT_UNEXPECTED) from exc

    if result.source_hash_status is not None:
        typer.echo(f"source_hash: {result.source_hash_status}")
    typer.echo(f"source: {result.source}")
    typer.echo(f"built: {result.out_dir}")
    typer.echo(f"content_hash: {result.content_hash}")
    typer.echo(f"artifact_sha256: {result.artifact_sha256}")


@pack_app.command(name="scaffold")
def pack_scaffold(
    pack: Annotated[
        str,
        typer.Option(
            "--pack",
            help=("Path to a source pack directory (explicit path only; 'sample' is rejected)."),
        ),
    ],
    scientific_name: Annotated[
        str,
        typer.Option("--scientific-name", help="Scientific name for the new taxon."),
    ],
    archetype: Annotated[
        str,
        typer.Option(
            "--archetype",
            help="Archetype (annual, biennial, ..., fungal; see dictionary/vocab).",
        ),
    ],
    use: Annotated[
        list[str],
        typer.Option(
            "--use",
            help="Use category (repeatable; at least one required).",
        ),
    ],
    src: Annotated[
        list[str] | None,
        typer.Option(
            "--src",
            help=("Source id (repeatable). Default: first id from sources.csv."),
        ),
    ] = None,
    rank: Annotated[
        str,
        typer.Option("--rank", help="Taxon rank."),
    ] = "species",
) -> None:
    """Scaffold a new taxon (adds a taxa.csv row and a facts file)."""
    if pack == "sample":
        typer.echo(
            "error: pack scaffold requires an explicit path; 'sample' is not "
            "allowed. Pass the path, e.g. src/agri_core/_samples/sample_pack.",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)

    source = Path(pack)
    if not scientific_name.strip():
        typer.echo("error: --scientific-name must not be empty", err=True)
        raise typer.Exit(EXIT_USAGE)
    if not use:
        typer.echo(
            "error: --use is required (at least one use category)",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)

    try:
        result = scaffold_taxon(
            source,
            scientific_name=scientific_name,
            archetype=archetype,
            rank=rank,
            uses=tuple(use),
            srcs=tuple(src) if src else None,
        )
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc
    except OSError as exc:
        typer.echo(f"error: OSError: {exc}", err=True)
        raise typer.Exit(EXIT_UNEXPECTED) from exc

    typer.echo(f"scaffolded: {result.taxon_id}")
    typer.echo(f"source: {result.source}")
    typer.echo(f"facts: {result.facts_path}")
    if result.content_hash_stale:
        typer.echo(
            "warning: source pack.toml declares content_hash; it is now stale. "
            "Run `agri-core pack lock --pack PATH` to update.",
            err=True,
        )


@app.command(name="diff")
def diff(
    old: Annotated[str, typer.Option("--old", help="Old pack directory or 'sample'.")],
    new: Annotated[str, typer.Option("--new", help="New pack directory or 'sample'.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a JSON DiffReport instead of text."),
    ] = False,
    exit_code: Annotated[
        bool,
        typer.Option(
            "--exit-code",
            help="Exit 1 on any difference, not only on violations.",
        ),
    ] = False,
) -> None:
    """Compare two packs. Violations exit 1; normal diffs exit 0 by default."""
    old_path = _resolve_pack_path(old)
    new_path = _resolve_pack_path(new)
    try:
        old_ks = load_knowledge_set(old_path, allow_synthetic=True)
        new_ks = load_knowledge_set(new_path, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    report = diff_packs(old_ks, new_ks)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(f"hashes: {report.old_pack_hash} -> {report.new_pack_hash}")
        typer.echo(
            f"taxa: added {len(report.taxa.added)}, "
            f"removed {len(report.taxa.removed)}, "
            f"changed {len(report.taxa.changed)}"
        )
        typer.echo(
            f"facts: added {len(report.facts_added)}, "
            f"removed {len(report.facts_removed)}, "
            f"changed {len(report.facts_changed)}"
        )
        for change in report.facts_changed:
            typer.echo(
                f"  {change.fact_id}: {change.classification} [{', '.join(change.fields_changed)}]"
            )
        if report.violations:
            typer.echo(f"violations: {len(report.violations)}")
            for v in report.violations:
                typer.echo(f"  {v.kind} {v.entity_id}: {v.message}", err=True)
        elif report.identical:
            typer.echo("no differences")

    if report.violations:
        raise typer.Exit(EXIT_ERROR)
    if exit_code and not report.identical:
        raise typer.Exit(EXIT_ERROR)


@app.command(name="coverage")
def coverage_cmd(
    pack: Annotated[
        str,
        typer.Option("--pack", help="Path to a pack directory, or 'sample'."),
    ],
    tier: Annotated[
        list[str] | None,
        typer.Option(
            "--tier",
            help="Exact tier filter (T0, T1, T2, T3); repeatable.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of text."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Show full lists instead of truncating."),
    ] = False,
) -> None:
    """Show tier distribution and per-taxon coverage.

    Tiers are derived from fact coverage; see ADR-003. The distribution
    summary counts every taxon in the pack; ``--tier`` filters only the
    per-taxon detail rows.
    """
    tier_filter: set[Tier] | None = None
    if tier:
        parsed: set[Tier] = set()
        for raw in tier:
            try:
                parsed.add(Tier(raw))
            except ValueError:
                valid = ", ".join(m.value for m in Tier)
                typer.echo(
                    f"error: invalid --tier {raw!r}; valid values: {valid}",
                    err=True,
                )
                raise typer.Exit(EXIT_USAGE) from None
        tier_filter = parsed

    path = _resolve_pack_path(pack)
    try:
        ks = load_knowledge_set(path, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    if ks.manifest.synthetic:
        typer.echo("SYNTHETIC DATA", err=True)

    dictionary = _default_dictionary()
    results = derive_all_tiers(ks, dictionary)

    summary = Counter(r.tier.value for r in results.values())

    if tier_filter is not None:
        shown = {tid: r for tid, r in results.items() if r.tier in tier_filter}
    else:
        shown = results

    tier_order = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
    sorted_taxa = sorted(
        shown.values(),
        key=lambda r: (tier_order[r.tier.value], r.taxon_id),
    )

    if json_output:
        payload = {
            "pack": {
                "name": ks.manifest.name,
                "version": ks.manifest.version,
                "synthetic": ks.manifest.synthetic,
            },
            "summary": {t.value: summary.get(t.value, 0) for t in Tier},
            "taxa": [
                {
                    "taxon_id": r.taxon_id,
                    "tier": r.tier.value,
                    "required_params": list(r.required_params),
                    "missing_params": list(r.missing_params),
                    "system_gaps": list(r.system_gaps),
                    "detail": r.detail,
                }
                for r in sorted_taxa
            ],
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    kind = "sample" if pack == "sample" else str(path.resolve())
    typer.echo(f"pack: {ks.manifest.name} {ks.manifest.version} ({kind})")
    typer.echo("")
    typer.echo("distribution:")
    for t in Tier:
        typer.echo(f"  {t.value}: {summary.get(t.value, 0)}")
    typer.echo("")
    if not sorted_taxa:
        typer.echo("no taxa match --tier filter")
        return
    typer.echo("taxa:")
    for r in sorted_taxa:
        typer.echo(
            f"  {r.taxon_id}  {r.tier.value}  "
            f"required={len(r.required_params)} "
            f"missing={len(r.missing_params)} "
            f"system_gaps={len(r.system_gaps)}"
        )
        for label, items in (
            ("missing", r.missing_params),
            ("system_gaps", r.system_gaps),
        ):
            if not items:
                continue
            if verbose or len(items) <= 3:
                typer.echo(f"    {label}: {', '.join(items)}")
            else:
                head_items = ", ".join(items[:3])
                typer.echo(f"    {label}: {head_items} (+{len(items) - 3} more)")


_STATUS_ORDER: dict[str, int] = {
    "imported": 0,
    "draft": 1,
    "reviewed": 2,
    "approved": 3,
}


@app.command(name="show")
def show_cmd(
    pack: Annotated[
        str,
        typer.Option("--pack", help="Path to a pack directory, or 'sample'."),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Resolve a taxon name."),
    ] = None,
    taxon: Annotated[
        str | None,
        typer.Option("--taxon", help="Show a taxon by taxon_id."),
    ] = None,
    fact: Annotated[
        str | None,
        typer.Option("--fact", help="Show a fact by fact_id."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of text."),
    ] = False,
    language: Annotated[
        str | None,
        typer.Option(
            "--language",
            help="Display name in this language (only with --name).",
        ),
    ] = None,
    min_status: Annotated[
        str | None,
        typer.Option("--min-status", help="Minimum fact status for --taxon."),
    ] = None,
    require_commercial: Annotated[
        bool,
        typer.Option(
            "--require-commercial",
            help="Only facts whose sources are all commercial_use=yes.",
        ),
    ] = False,
) -> None:
    """Show a resolution outcome, a taxon, or a fact from a pack."""
    flags = [name is not None, taxon is not None, fact is not None]
    if sum(flags) != 1:
        typer.echo("error: specify exactly one of --name, --taxon, --fact", err=True)
        raise typer.Exit(EXIT_USAGE)
    if language is not None and name is None:
        typer.echo("error: --language only valid with --name", err=True)
        raise typer.Exit(EXIT_USAGE)
    if (min_status is not None or require_commercial) and taxon is None:
        typer.echo(
            "error: --min-status and --require-commercial only valid with --taxon",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)
    if min_status is not None and min_status not in _STATUS_ORDER:
        valid = ", ".join(_STATUS_ORDER)
        typer.echo(
            f"error: invalid --min-status {min_status!r}; valid: {valid}",
            err=True,
        )
        raise typer.Exit(EXIT_USAGE)

    path = _resolve_pack_path(pack)
    try:
        ks = load_knowledge_set(path, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    if ks.manifest.synthetic:
        typer.echo("SYNTHETIC DATA", err=True)

    if name is not None:
        rc = _show_name(ks, name, json_output=json_output, language=language)
    elif taxon is not None:
        rc = _show_taxon(
            ks,
            taxon,
            json_output=json_output,
            min_status=min_status,
            require_commercial=require_commercial,
        )
    else:
        assert fact is not None
        rc = _show_fact(ks, fact, json_output=json_output)
    if rc != EXIT_OK:
        raise typer.Exit(rc)


def _show_name(
    ks: KnowledgeSet,
    name: str,
    *,
    json_output: bool,
    language: str | None,
) -> int:
    outcome = resolve_taxon(ks, name)
    if isinstance(outcome, TaxonOk):
        display = outcome.name
        if language is not None:
            for n in ks.names_for(outcome.taxon_id):
                if n.language == language:
                    display = n.name
                    break
        if json_output:
            payload = outcome.model_dump(mode="json")
            payload["name"] = display
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        else:
            typer.echo(f"ok: {outcome.taxon_id} {display} via={outcome.matched_via}")
        return EXIT_OK
    if isinstance(outcome, Ambiguous):
        if json_output:
            typer.echo(json.dumps(outcome.model_dump(mode="json"), indent=2, sort_keys=True))
        else:
            flag = "true" if outcome.truncated else "false"
            typer.echo(f"ambiguous: {len(outcome.candidates)} candidates truncated={flag}")
            for c in outcome.candidates:
                note_part = f" ({c.note})" if c.note else ""
                typer.echo(f"  {c.taxon_id} {c.name}{note_part}")
        return EXIT_ERROR
    if json_output:
        typer.echo(json.dumps(outcome.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        code_part = f" code={outcome.code}" if outcome.code else ""
        typer.echo(f"unknown: {outcome.reason}{code_part}")
    return EXIT_ERROR


def _fact_is_commercial(ks: KnowledgeSet, fact: FactRow) -> bool:
    for sid in fact.src or ():
        try:
            src = ks.source(sid)
        except KeyError:
            return False
        if src.commercial_use != "yes":
            return False
    return True


def _show_taxon(
    ks: KnowledgeSet,
    taxon_id: str,
    *,
    json_output: bool,
    min_status: str | None,
    require_commercial: bool,
) -> int:
    try:
        row = ks.taxon(taxon_id)
    except KeyError:
        typer.echo(f"error: taxon {taxon_id!r} not found", err=True)
        return EXIT_ERROR

    facts = list(ks.facts_for(taxon_id))
    if min_status is not None:
        floor = _STATUS_ORDER[min_status]
        facts = [f for f in facts if _STATUS_ORDER[f.status] >= floor]
    if require_commercial:
        facts = [f for f in facts if _fact_is_commercial(ks, f)]

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "taxon": row.model_dump(mode="json"),
                    "facts": [f.model_dump(mode="json") for f in facts],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        typer.echo(
            f"taxon: {row.taxon_id} {row.scientific_name} "
            f"rank={row.rank} archetype={row.archetype} "
            f"organism_group={row.organism_group}"
        )
        for f in facts:
            pretty = format_value(f.value)
            typer.echo(f"  {f.fact_id} {f.parameter}={pretty} status={f.status}")
    return EXIT_OK


def _show_fact(ks: KnowledgeSet, fact_id: str, *, json_output: bool) -> int:
    target: FactRow | None = None
    for f in ks.facts():
        if f.fact_id == fact_id:
            target = f
            break
    if target is None:
        typer.echo(f"error: fact {fact_id!r} not found", err=True)
        return EXIT_ERROR
    if json_output:
        typer.echo(json.dumps(target.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        pretty = format_value(target.value)
        typer.echo(
            f"fact: {target.fact_id} taxon={target.taxon_id} "
            f"parameter={target.parameter} value={pretty} status={target.status}"
        )
    return EXIT_OK


def main() -> NoReturn:
    try:
        app()
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        raise SystemExit(EXIT_UNEXPECTED) from exc
    raise SystemExit(EXIT_OK)


if __name__ == "__main__":
    main()
