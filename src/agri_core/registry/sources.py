"""Source-row model and linting for ``sources.csv``."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

CommercialUse = Literal["yes", "no", "unclear"]

CSV_HEADER: list[str] = [
    "id",
    "url",
    "license",
    "commercial_use",
    "access_date",
    "citation",
]

_SPDX_LIKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")
_LICENSE_REF = re.compile(r"^LicenseRef-[A-Za-z0-9][A-Za-z0-9.-]*$")


def is_nc_license(license_id: str) -> bool:
    """Detect non-commercial licenses by token, not substring.

    Splits on ``-`` and looks for ``nc`` or ``noncommercial`` tokens, so
    ``CC-BY-NC-4.0`` matches but ``unclear`` and ``NCBI`` do not.
    """
    tokens = [token.lower() for token in license_id.split("-")]
    return "nc" in tokens or "noncommercial" in tokens


def is_sa_license(license_id: str) -> bool:
    """True if *license_id* names a ShareAlike variant.

    Splits on ``-`` and looks for ``sa`` or ``sharealike`` tokens, so
    ``CC-BY-SA-4.0`` matches but ``NASDAQ`` does not.
    """
    tokens = {tok.lower() for tok in license_id.split("-")}
    return "sa" in tokens or "sharealike" in tokens


def is_nd_license(license_id: str) -> bool:
    """True if *license_id* names a NoDerivatives variant.

    Splits on ``-`` and looks for ``nd``, ``noderiv``, or
    ``noderivatives`` tokens, so ``CC-BY-ND-4.0`` matches but ``INDIA``
    does not.
    """
    tokens = {tok.lower() for tok in license_id.split("-")}
    return "nd" in tokens or "noderiv" in tokens or "noderivatives" in tokens


def _is_valid_license(license_id: str) -> bool:
    if license_id == "unclear":
        return True
    if _LICENSE_REF.match(license_id):
        return True
    return bool(_SPDX_LIKE.match(license_id))


class SourceRow(BaseModel):
    """One row of ``sources.csv``."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: str = Field(pattern=r"^S\d{3,}$")
    url: str
    license: str
    commercial_use: CommercialUse
    access_date: date
    citation: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"url scheme must be http or https, got {parts.scheme!r}")
        if not parts.netloc:
            raise ValueError("url must include a host")
        return value

    @field_validator("license")
    @classmethod
    def _check_license(cls, value: str) -> str:
        if not _is_valid_license(value):
            raise ValueError(
                f"license must be 'unclear', 'LicenseRef-<slug>', or an SPDX-like ID; got {value!r}"
            )
        return value

    @field_validator("commercial_use", mode="before")
    @classmethod
    def _normalize_commercial_use(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


@dataclass(frozen=True)
class Finding:
    """One problem found while linting ``sources.csv``."""

    code: str
    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None
    message: str


def _row_findings(row: SourceRow, line: int, *, today: date, filename: str) -> list[Finding]:
    out: list[Finding] = []
    if row.access_date > today:
        out.append(
            Finding(
                code="SRC004",
                severity="error",
                file=filename,
                line=line,
                message=f"{row.id}: access_date {row.access_date} is in the future",
            )
        )
    if row.commercial_use == "yes":
        if row.license == "unclear":
            out.append(
                Finding(
                    code="SRC002",
                    severity="error",
                    file=filename,
                    line=line,
                    message=f"{row.id}: commercial_use=yes requires a known license",
                )
            )
        elif is_nc_license(row.license):
            out.append(
                Finding(
                    code="SRC001",
                    severity="error",
                    file=filename,
                    line=line,
                    message=(
                        f"{row.id}: commercial_use=yes conflicts with NC license {row.license}"
                    ),
                )
            )
    return out


def lint_csv_text(
    text: str,
    *,
    today: date,
    filename: str = "<inline>",
) -> list[Finding]:
    """Lint an in-memory CSV text. Returns every finding; never stops early."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text))
    findings: list[Finding] = []
    try:
        header = next(reader)
    except StopIteration:
        findings.append(Finding("SRC100", "error", filename, None, "empty file"))
        return findings
    if header != CSV_HEADER:
        findings.append(
            Finding(
                "SRC101",
                "error",
                filename,
                1,
                f"header mismatch: expected {CSV_HEADER!r}, got {header!r}",
            )
        )
        return findings
    seen: dict[str, int] = {}
    for csv_row in reader:
        line = reader.line_num
        if not csv_row or all(cell == "" for cell in csv_row):
            continue
        if len(csv_row) != len(CSV_HEADER):
            findings.append(
                Finding(
                    "SRC102",
                    "error",
                    filename,
                    line,
                    f"row has {len(csv_row)} fields, expected {len(CSV_HEADER)}",
                )
            )
            continue
        record = dict(zip(CSV_HEADER, csv_row, strict=True))
        try:
            row = SourceRow.model_validate(record)
        except ValueError as exc:
            findings.append(Finding("SRC103", "error", filename, line, f"invalid row: {exc}"))
            continue
        if row.id in seen:
            findings.append(
                Finding(
                    "SRC104",
                    "error",
                    filename,
                    line,
                    f"{row.id}: duplicate id (first at line {seen[row.id]})",
                )
            )
            continue
        seen[row.id] = line
        findings.extend(_row_findings(row, line, today=today, filename=filename))
    return findings


def lint_csv_file(path: Path, *, today: date) -> list[Finding]:
    if not path.is_file():
        return [Finding("SRC000", "error", str(path), None, "sources file not found")]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    return lint_csv_text(text, today=today, filename=str(path))
