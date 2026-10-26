"""agri-core command line."""

from __future__ import annotations

import contextlib
import csv
import io
import json
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
    load_knowledge_set,
    load_knowledge_set_from_files,
    parse_manifest_bytes,
    read_pack_bytes,
)
from agri_core.pack.sqlite_schema import write_built_pack
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
        load_knowledge_set_from_files(files, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    if errors:
        raise typer.Exit(EXIT_ERROR)


def _render_pack_toml(manifest: PackManifest, content_hash: str) -> str:
    """Render pack.toml with a fixed key order (comments are not preserved)."""
    lines = [
        f"name = {json.dumps(manifest.name)}",
        f"version = {json.dumps(manifest.version)}",
        f"schema_version = {manifest.schema_version}",
        f"engine_min = {json.dumps(manifest.engine_min)}",
        f"dictionary_min = {json.dumps(manifest.dictionary_min)}",
        f"synthetic = {'true' if manifest.synthetic else 'false'}",
        f"content_hash = {json.dumps(content_hash)}",
    ]
    return "\n".join(lines) + "\n"


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
        load_knowledge_set_from_files(files, allow_synthetic=True)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    # Compute the hash from the content we are about to write, not from the
    # current pack.toml (which may lack fields such as `synthetic` that
    # _render_pack_toml normalizes in).
    content_without_hash = _render_pack_toml(manifest, "")
    files_with_new_toml = dict(files)
    files_with_new_toml["pack.toml"] = content_without_hash.encode("utf-8")
    new_hash = hash_pack_files(files_with_new_toml)
    content = _render_pack_toml(manifest, new_hash)

    target = path / "pack.toml"
    tmp = path / "pack.toml.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
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


def _strip_content_hash(toml_bytes: bytes) -> bytes:
    """Remove the content_hash line so structural validation skips hash check."""
    text = toml_bytes.decode("utf-8")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("content_hash")]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _reject_existing_artifacts(out_dir: Path) -> None:
    for name in ("pack.sqlite", "pack.toml"):
        target = out_dir / name
        if target.exists():
            typer.echo(
                f"error: {target} already exists; remove it or choose another --out",
                err=True,
            )
            raise typer.Exit(EXIT_USAGE)


def _sync_source_hash(
    source: Path, files: Mapping[str, bytes], manifest: PackManifest
) -> tuple[str, dict[str, bytes]]:
    """Rewrite source pack.toml canonically. Returns (status, files_with_fresh_toml)."""
    computed = hash_pack_files(files)
    fresh_bytes = _render_pack_toml(manifest, computed).encode("utf-8")
    if manifest.content_hash == computed and files["pack.toml"] == fresh_bytes:
        return "unchanged", dict(files)
    status = "updated" if manifest.content_hash != computed else "normalized"
    target = source / "pack.toml"
    tmp = source / "pack.toml.tmp"
    try:
        tmp.write_bytes(fresh_bytes)
        os.replace(tmp, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        typer.echo(f"error: OSError: {exc}", err=True)
        raise typer.Exit(EXIT_UNEXPECTED) from exc
    return status, {**files, "pack.toml": fresh_bytes}


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

    source = Path(pack)
    try:
        files: Mapping[str, bytes] = read_pack_bytes(source)
        manifest = parse_manifest_bytes(files["pack.toml"])

        if update_source_hash:
            stripped = {
                **files,
                "pack.toml": _strip_content_hash(files["pack.toml"]),
            }
            load_knowledge_set_from_files(stripped, allow_synthetic=True)
            status, files_new = _sync_source_hash(source, files, manifest)
            typer.echo(f"source_hash: {status}")
            files = files_new
        else:
            load_knowledge_set(source, allow_synthetic=True)

        write_built_pack(files, out_dir=out_dir)
        built = parse_manifest_bytes((out_dir / "pack.toml").read_bytes())
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        for finding in getattr(exc, "findings", ()):
            loc = f"{finding.file}:{finding.line}" if getattr(finding, "file", None) else "-"
            typer.echo(f"  {finding.code} {loc}: {finding}", err=True)
        raise typer.Exit(EXIT_PACK) from exc

    typer.echo(f"source: {source}")
    typer.echo(f"built: {out_dir}")
    typer.echo(f"content_hash: {built.content_hash}")
    typer.echo(f"artifact_sha256: {built.artifact_sha256}")


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
