"""agri-core command line."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from jsonschema import Draft202012Validator

from agri_core import __version__
from agri_core.registry import (
    DataNotFoundError,
    Finding,
    lint_csv_file,
    resolve_data_root,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DATA_NOT_FOUND = 3

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


def _open_data_root(data_dir: Path | None) -> tuple[Path, str]:
    try:
        root = resolve_data_root(override=data_dir)
    except DataNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_DATA_NOT_FOUND) from exc
    return root.path, root.kind


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


@app.command(name="lint-sources")
def lint_sources(
    data_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--data-dir",
            help="Explicit data root (must contain profiles/sources.csv and schema/).",
        ),
    ] = None,
) -> None:
    """Check profiles/sources.csv for schema and consistency errors."""
    root, kind = _open_data_root(data_dir)
    typer.echo(f"data: {kind}")
    sources_csv = root / "profiles" / "sources.csv"
    findings = lint_csv_file(sources_csv, today=date.today())
    errors, warnings = _emit_findings(findings)
    counts = _count_commercial_use(sources_csv)
    typer.echo(
        f"sources: {sum(counts.values())} "
        f"(yes: {counts['yes']}, no: {counts['no']}, unclear: {counts['unclear']})"
    )
    typer.echo(f"errors: {errors}, warnings: {warnings}")
    if errors:
        raise typer.Exit(EXIT_ERROR)


@app.command(name="validate")
def validate(
    data_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--data-dir",
            help="Explicit data root (must contain profiles/sources.csv and schema/).",
        ),
    ] = None,
) -> None:
    """Lint sources and verify every schema under schema/ is a valid JSON Schema."""
    root, kind = _open_data_root(data_dir)
    typer.echo(f"agri-core {__version__} | data: {kind}")

    findings = lint_csv_file(root / "profiles" / "sources.csv", today=date.today())
    errors, warnings = _emit_findings(findings)

    schema_dir = root / "schema"
    schema_files = sorted(schema_dir.glob("*.schema.json"))
    for schema_path in schema_files:
        try:
            doc = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(doc)
        except Exception as exc:
            typer.echo(f"error: SCHEMA {schema_path.name}: {exc}")
            errors += 1

    counts = _count_commercial_use(root / "profiles" / "sources.csv")
    typer.echo("profiles: 0")
    typer.echo(
        f"sources: {sum(counts.values())} "
        f"(yes: {counts['yes']}, no: {counts['no']}, unclear: {counts['unclear']})"
    )
    typer.echo(f"schemas: {len(schema_files)}")
    typer.echo(f"errors: {errors}, warnings: {warnings}")

    if errors:
        raise typer.Exit(EXIT_ERROR)


if __name__ == "__main__":
    app()
