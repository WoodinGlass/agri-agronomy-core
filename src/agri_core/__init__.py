"""agri-agronomy-core: offline, deterministic crop profiles and agronomy calculators."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agri-agronomy-core")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0+unknown"

__all__ = ["__version__"]
