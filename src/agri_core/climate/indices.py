"""Generic climate index engine driven by dictionary/vocab/climate_indices.yaml.

Each registered index names a source (see the YAML `description` field);
the engine implements the threshold/window/aggregation recipe, not the
agronomic interpretation.

Output unit depends on aggregation:
- ``count`` and ``max_run`` return a count of days (``unit = "day"``).
- ``sum``, ``min``, ``max``, ``max_rolling_sum`` return a value in the
  registry's ``unit`` (the unit of the input series).
The ``operator``/``threshold`` pair is used only by ``count`` and
``max_run``; the aggregate aggregations ignore them (they exist for
schema uniformity).
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, cast

import yaml

from agri_core.models import (
    Notice,
    Outcome,
    Provenance,
    Subject,
    compute_request_id,
    insufficient_input,
    ok,
)

__all__ = ["threshold_index"]

_CALC_VERSION = "0.1.0"


def _registry_source() -> Any:
    """Return a path-like source for climate_indices.yaml.

    Prefer the packaged file (``agri_core/_dictionary/vocab/climate_indices.yaml``);
    fall back to the source tree during development.
    """
    try:
        from importlib.resources import files as _files

        pkg = _files("agri_core") / "_dictionary" / "vocab" / "climate_indices.yaml"
        if pkg.is_file():
            return pkg
    except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError):
        pass
    return Path(__file__).resolve().parents[3] / "dictionary" / "vocab" / "climate_indices.yaml"


@functools.lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, Any]]:
    source = _registry_source()
    text = source.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    indices = data["indices"]
    assert isinstance(indices, dict), "climate_indices.yaml 'indices' is not a dict"
    return cast("dict[str, dict[str, Any]]", indices)


def _check_consecutive_dates(dates: Sequence[date]) -> list[str]:
    problems: list[str] = []
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if delta != 1:
            problems.append(f"gap_between_{dates[i - 1].isoformat()}_and_{dates[i].isoformat()}")
    return problems


def _apply_operator(value: float, operator: str, threshold: float) -> bool:
    if operator == "lt":
        return value < threshold
    if operator == "le":
        return value <= threshold
    if operator == "gt":
        return value > threshold
    if operator == "ge":
        return value >= threshold
    raise ValueError(f"unknown operator: {operator!r}")


def _max_run(matches: list[bool]) -> int:
    best = 0
    cur = 0
    for m in matches:
        if m:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def threshold_index(
    *,
    index_name: str,
    dates: Sequence[date],
    values: Sequence[float],
    threshold_override: float | None = None,
) -> Outcome:
    """Apply a registered climate index to a daily series.

    ``dates`` must be consecutive (one day apart). A gap returns
    ``insufficient_input`` with the gap description.

    ``threshold_override`` replaces the registry threshold (for example a
    crop-specific frost tolerance). When set, an assumption
    ``threshold_override_applied`` is emitted; when unset, the registry
    default emits ``threshold_default_from_registry``.
    """
    registry = _load_registry()
    inputs = {
        "index_name": index_name,
        "n": len(dates),
        "first_date": dates[0].isoformat() if dates else None,
        "last_date": dates[-1].isoformat() if dates else None,
        "threshold_override": threshold_override,
    }
    subject = Subject(calculation="threshold_index", calculation_version=_CALC_VERSION)
    request_id = compute_request_id(subject=subject, inputs=inputs)

    if not dates or not values:
        return insufficient_input(missing=["empty_series"], subject=subject, request_id=request_id)
    if len(dates) != len(values):
        raise ValueError(f"length mismatch: dates={len(dates)}, values={len(values)}")
    if index_name not in registry:
        return insufficient_input(
            missing=[f"unknown_index:{index_name}"],
            subject=subject,
            request_id=request_id,
        )

    problems = _check_consecutive_dates(dates)
    if problems:
        return insufficient_input(missing=problems, subject=subject, request_id=request_id)

    spec = registry[index_name]
    operator = spec["operator"]
    aggregation = spec["aggregation"]
    window_days = spec.get("window_days")

    # Threshold handling
    if threshold_override is not None:
        effective_threshold: float | None = threshold_override
        assumptions = [
            Notice(
                code="threshold_override_applied",
                message=(
                    f"threshold {threshold_override} overrides registry default for {index_name!r}"
                ),
            )
        ]
    else:
        effective_threshold = spec.get("threshold")
        if effective_threshold is not None:
            assumptions = [
                Notice(
                    code="threshold_default_from_registry",
                    message=(f"threshold {effective_threshold} from registry {index_name!r}"),
                )
            ]
        else:
            assumptions = []

    # Compute
    if aggregation == "count":
        if effective_threshold is None:
            raise ValueError(f"{index_name}: count requires a threshold")
        n = sum(1 for v in values if _apply_operator(v, operator, effective_threshold))
        value = float(n)
        unit = "day"
    elif aggregation == "max_run":
        if effective_threshold is None:
            raise ValueError(f"{index_name}: max_run requires a threshold")
        matches = [_apply_operator(v, operator, effective_threshold) for v in values]
        value = float(_max_run(matches))
        unit = "day"
    elif aggregation == "max_rolling_sum":
        if window_days is None:
            raise ValueError(f"{index_name}: max_rolling_sum requires window_days")
        if len(values) < window_days:
            return insufficient_input(
                missing=[f"series_length_{len(values)}_lt_window_{window_days}"],
                subject=subject,
                request_id=request_id,
            )
        windows = [sum(values[i : i + window_days]) for i in range(len(values) - window_days + 1)]
        value = float(max(windows))
        unit = spec["unit"]
    elif aggregation == "sum":
        value = float(sum(values))
        unit = spec["unit"]
    elif aggregation == "min":
        value = float(min(values))
        unit = spec["unit"]
    elif aggregation == "max":
        value = float(max(values))
        unit = spec["unit"]
    else:
        raise ValueError(f"unknown aggregation: {aggregation!r}")

    return ok(
        value=value,
        unit=unit,
        method=f"registry:{index_name}",
        provenance=Provenance(),
        evidence=[],
        assumptions=assumptions,
        subject=subject,
        request_id=request_id,
    )
