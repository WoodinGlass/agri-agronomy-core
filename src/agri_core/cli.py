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
from agri_core.models.finding import Finding, FindingSeverity
from agri_core.pack import (
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
from agri_core.pack.validate import validate_pack
from agri_core.registry import lint_csv_text

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


def _load_and_print(spec: str) -> tuple[Mapping[str, bytes], PackManifest]:
    path = _resolve_pack_path(spec)
    try:
        files = read_pack_bytes(path)
        manifest = parse_manifest_bytes(files["pack.toml"])
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

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
) -> None:
    """Validate a pack: manifest, sources, and structural integrity.

    Inspection only; always accepts synthetic packs. The SYNTHETIC DATA
    banner on stderr is the warning. Only calculation commands (M8+)
    require an explicit opt-in for synthetic data.
    """
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

    try:
        validate_pack(files, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    if errors:
        raise typer.Exit(EXIT_ERROR)


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
