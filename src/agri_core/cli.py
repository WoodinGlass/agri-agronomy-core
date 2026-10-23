"""agri-core command line."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from agri_core import __version__
from agri_core.pack import (
    Pack,
    PackError,
    load_pack,
    load_sample_pack,
)
from agri_core.registry import Finding, lint_csv_file

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


def _resolve_pack(spec: str) -> Pack:
    try:
        if spec == "sample":
            return load_sample_pack()
        return load_pack(spec)
    except PackError as exc:
        typer.echo(f"error: {exc.code}: {exc}", err=True)
        raise typer.Exit(EXIT_PACK) from exc


def _print_pack_line(pack: Pack) -> None:
    kind = "sample" if pack.kind == "sample" else str(pack.root.resolve())
    typer.echo(f"pack: {pack.manifest.name} {pack.manifest.version} ({kind})")


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


def _count_commercial_use(sources_csv: Path) -> dict[str, int]:
    counts = {"yes": 0, "no": 0, "unclear": 0}
    if not sources_csv.is_file():
        return counts
    with sources_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row or not any(v for v in row.values() if v):
                continue
            cu = (row.get("commercial_use") or "").strip().lower()
            if cu in counts:
                counts[cu] += 1
    return counts


@app.command(name="lint-sources")
def lint_sources(
    pack: Annotated[
        str,
        typer.Option("--pack", help="Path to a pack directory, or 'sample'."),
    ],
) -> None:
    """Check a pack's sources.csv for schema and consistency errors."""
    p = _resolve_pack(pack)
    _print_pack_line(p)
    findings = lint_csv_file(p.sources_csv, today=date.today())
    errors, warnings = _emit_findings(findings)
    counts = _count_commercial_use(p.sources_csv)
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
    """Validate a pack: manifest and sources.csv."""
    p = _resolve_pack(pack)
    _print_pack_line(p)
    findings = lint_csv_file(p.sources_csv, today=date.today())
    errors, warnings = _emit_findings(findings)
    counts = _count_commercial_use(p.sources_csv)
    typer.echo("profiles: 0")
    typer.echo(
        f"sources: {sum(counts.values())} "
        f"(yes: {counts['yes']}, no: {counts['no']}, unclear: {counts['unclear']})"
    )
    typer.echo(f"errors: {errors}, warnings: {warnings}")
    if errors:
        raise typer.Exit(EXIT_ERROR)


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
