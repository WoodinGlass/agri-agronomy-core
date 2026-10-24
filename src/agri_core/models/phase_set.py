"""PhaseSet model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PhaseSetSource = Literal["none", "biological", "kc", "custom"]


class PhaseSet(BaseModel):
    """A named axis of phases along which parameter values may vary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: PhaseSetSource
    phases: list[str] = Field(default_factory=list)
    description: str | None = None
