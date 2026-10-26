"""agri-core command line."""

from __future__ import annotations

import contextlib
import csv
import io
import os
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from agri_core import __version__
from agri_core.pack import (
    PackError,
    PackManifest,
    compute_pack_hash,
    hash_pack_files,
    parse_manifest_bytes,
    read_pack_bytes,
)
from agri_core.pack.build import build_pack, render_source_manifest
from agri_core.pack.validate import validate_pack
from agri_core.registry import Finding, lint_csv_text

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
        loc = f"{f.file}:{f.line}" if f.line else f.file
        typer.echo(f"{f.severity}: {f.code} {loc}: {f.message}")
        if f.severity == "error":
            errors += 1
        elif f.severity == "warning":
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
