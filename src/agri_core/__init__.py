"""agri-agronomy-core: offline, deterministic crop profiles and agronomy calculators."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agri-agronomy-core")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.1+unknown"

RESOLUTION_POLICY_VERSION = "1.1.0"
"""SemVer of the fact/taxon resolution policy (ADR-004).

Distinct from ``__version__``: the engine can release without changing
resolution behavior, and the policy can bump without an engine release
number change. A consumer that wants stable resolution behavior pins
this, not ``__version__``. See ADR-004 section "resolution policy version".
"""

__all__ = ["RESOLUTION_POLICY_VERSION", "__version__"]
