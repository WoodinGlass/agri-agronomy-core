"""Dataset row: an external data source cited by facts."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agri_core.models.ids import DatasetId

_SPDX_LIKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")
_LICENSE_REF = re.compile(r"^LicenseRef-[A-Za-z0-9][A-Za-z0-9.-]*$")
_CHECKSUM = re.compile(r"^sha256:[a-f0-9]{64}$")


def _valid_license(v: str) -> bool:
    if v == "unclear":
        return True
    if _LICENSE_REF.match(v):
        return True
    return bool(_SPDX_LIKE.match(v))


class DatasetRow(BaseModel):
    """One row of ``datasets.csv``: an external dataset a fact cites.

    ``license`` accepts SPDX-shaped identifiers, ``LicenseRef-<slug>`` for
    custom licenses, or ``unclear`` when the license is unknown. Full SPDX
    membership is checked at validate time against the manifest's
    dictionary_version, not here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    dataset_id: DatasetId
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    license: str
    checksum: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    url: str | None = None
    locator: str | None = None
    access_date: date

    @field_validator("license")
    @classmethod
    def _check_license(cls, v: str) -> str:
        if not _valid_license(v):
            raise ValueError(
                f"license must be 'unclear', 'LicenseRef-<slug>', or an SPDX-like ID; got {v!r}"
            )
        return v

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"url scheme must be http or https, got {parts.scheme!r}")
        if not parts.netloc:
            raise ValueError("url must include a host")
        return v

    @model_validator(mode="after")
    def _require_url_or_locator(self) -> DatasetRow:
        if self.url is None and self.locator is None:
            raise ValueError("at least one of url or locator is required")
        return self
