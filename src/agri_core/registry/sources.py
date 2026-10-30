"""Source-row model and linting for ``sources.csv``."""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agri_core.models.finding import Finding, FindingLocation, FindingSeverity

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


_ALLOWED_LICENSES: frozenset[str] = frozenset(
    {
        "CC0-1.0",
        "CC-BY-3.0",
        "CC-BY-4.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "LicenseRef-PublicDomain",
    }
)
"""Commercial-use allowlist for data sources (exact-match SPDX IDs).

See ADR-005. Adding a license here requires an ADR amendment and a
CHANGELOG entry.
"""

_ALLOWED_LICENSES_DATASET: frozenset[str] = _ALLOWED_LICENSES - {"LicenseRef-PublicDomain"}
"""Dataset allowlist: same as sources, without LicenseRef-PublicDomain.

Datasets have no ``citation`` column in 0.1.2, so a PD dataset cannot
record the ``basis:`` justification required for sources. PD datasets
are rejected outright until a schema change lands.
"""

_PD_SENTINEL = "LicenseRef-PublicDomain"
_PD_BASIS_PREFIX = "basis:"

_COMPOSITE_MARKERS = (" AND ", " OR ", " WITH ", "+")
"""Any of these in a license id means a composite SPDX expression.

Rejected unconditionally: a pack row records exactly one license it
relies on. A dual-license source is recorded as the single license the
pack uses.
"""


def is_allowed_license(license_id: str, *, for_dataset: bool = False) -> bool:
    """True if *license_id* is on the commercial-use allowlist.

    Fail-closed and exact-match on SPDX canonical identifiers. Rejected
    regardless of which allowlist is used:

    - Empty string, ``unclear``, ``NOASSERTION``.
    - Composite SPDX expressions (``AND``, ``OR``, ``WITH``, ``+``).
    - Unknown ``LicenseRef-*`` ids (only ``LicenseRef-PublicDomain`` is
      accepted, and only for sources with a ``basis:`` citation).

    ``LicenseRef-PublicDomain`` is rejected for datasets in 0.1.2: the
    dataset table has no ``citation`` column to record the basis.

    Blocklist findings remain as independent checks (ADR-005 point 4).
    """
    if not license_id or license_id == "unclear" or license_id == "NOASSERTION":
        return False
    if any(marker in license_id for marker in _COMPOSITE_MARKERS):
        return False
    if license_id.startswith("LicenseRef-") and license_id != _PD_SENTINEL:
        return False
    if is_nc_license(license_id) or is_sa_license(license_id) or is_nd_license(license_id):
        return False
    allowed = _ALLOWED_LICENSES_DATASET if for_dataset else _ALLOWED_LICENSES
    return license_id in allowed


def has_pd_basis(citation: str | None) -> bool:
    """True if *citation* begins with ``basis:`` (case-sensitive)."""
    if not citation:
        return False
    return citation.startswith(_PD_BASIS_PREFIX)


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


def _row_findings(row: SourceRow, line: int, *, today: date, filename: str) -> list[Finding]:
    out: list[Finding] = []
    if row.access_date > today:
        out.append(
            Finding(
                code="SRC004",
                severity=FindingSeverity.ERROR,
                message=f"{row.id}: access_date {row.access_date} is in the future",
                location=FindingLocation(file=filename, line=line),
            )
        )
    if row.commercial_use != "yes":
        out.append(
            Finding(
                code="SRC005",
                severity=FindingSeverity.ERROR,
                message=(
                    f"{row.id}: commercial_use={row.commercial_use!r} is not "
                    f"permitted; every source must be commercial_use=yes (ADR-005)"
                ),
                location=FindingLocation(file=filename, line=line),
            )
        )
    if row.commercial_use == "yes":
        if row.license == "unclear":
            out.append(
                Finding(
                    code="SRC002",
                    severity=FindingSeverity.ERROR,
                    message=f"{row.id}: commercial_use=yes requires a known license",
                    location=FindingLocation(file=filename, line=line),
                )
            )
        elif is_nc_license(row.license):
            out.append(
                Finding(
                    code="SRC001",
                    severity=FindingSeverity.ERROR,
                    message=(
                        f"{row.id}: commercial_use=yes conflicts with NC license {row.license}"
                    ),
                    location=FindingLocation(file=filename, line=line),
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
        findings.append(
            Finding(
                code="SRC100",
                severity=FindingSeverity.ERROR,
                message="empty file",
                location=FindingLocation(file=filename),
            )
        )
        return findings
    if header != CSV_HEADER:
        findings.append(
            Finding(
                code="SRC101",
                severity=FindingSeverity.ERROR,
                message=f"header mismatch: expected {CSV_HEADER!r}, got {header!r}",
                location=FindingLocation(file=filename, line=1),
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
                    code="SRC102",
                    severity=FindingSeverity.ERROR,
                    message=f"row has {len(csv_row)} fields, expected {len(CSV_HEADER)}",
                    location=FindingLocation(file=filename, line=line),
                )
            )
            continue
        record = dict(zip(CSV_HEADER, csv_row, strict=True))
        try:
            row = SourceRow.model_validate(record)
        except ValueError as exc:
            findings.append(
                Finding(
                    code="SRC103",
                    severity=FindingSeverity.ERROR,
                    message=f"invalid row: {exc}",
                    location=FindingLocation(file=filename, line=line),
                )
            )
            continue
        if row.id in seen:
            findings.append(
                Finding(
                    code="SRC104",
                    severity=FindingSeverity.ERROR,
                    message=f"{row.id}: duplicate id (first at line {seen[row.id]})",
                    location=FindingLocation(file=filename, line=line),
                )
            )
            continue
        seen[row.id] = line
        findings.extend(_row_findings(row, line, today=today, filename=filename))
    return findings


def lint_csv_file(path: Path, *, today: date) -> list[Finding]:
    if not path.is_file():
        return [
            Finding(
                code="SRC000",
                severity=FindingSeverity.ERROR,
                message="sources file not found",
                location=FindingLocation(file=str(path)),
            )
        ]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    return lint_csv_text(text, today=today, filename=str(path))
