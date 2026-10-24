"""ScopeKey model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScopeKeyType = Literal["string", "enum", "range"]


class ScopeKey(BaseModel):
    """One allowed key in a fact's scope object.

    * ``string``: free-form string (``multi=True`` allows an array).
    * ``enum``: value must be in ``vocab`` or ``values``.
    * ``range``: two-element ``[min, max]``; ``unit`` is required.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: ScopeKeyType
    vocab: str | None = None
    values: list[str] | None = None
    multi: bool = True
    unit: str | None = None

    @model_validator(mode="after")
    def _check_type_consistency(self) -> ScopeKey:
        if self.type == "range":
            if self.unit is None:
                raise ValueError("type=range requires unit")
        else:
            if self.unit is not None:
                raise ValueError(f"type={self.type} must have unit=null")

        if self.type == "enum" and self.vocab is None and self.values is None:
            raise ValueError("type=enum requires vocab or values")

        if self.vocab is not None and self.values is not None:
            raise ValueError("scope key cannot have both vocab and values")

        return self
