"""Climate parameter catalog: loader, lint, and shipped excluded list."""

from __future__ import annotations

from agri_core.catalog.excluded import (
    EXCLUDED_PARAM_IDS,
    is_excluded,
    matches_excluded,
)
from agri_core.catalog.lint import lint_catalog
from agri_core.catalog.loader import CatalogLoadError, load_catalog
from agri_core.catalog.models import (
    CatalogKind,
    CatalogOwner,
    CatalogRow,
    CatalogSafetyTier,
    CatalogStatus,
    CommercialUse,
)

__all__ = [
    "EXCLUDED_PARAM_IDS",
    "CatalogKind",
    "CatalogLoadError",
    "CatalogOwner",
    "CatalogRow",
    "CatalogSafetyTier",
    "CatalogStatus",
    "CommercialUse",
    "is_excluded",
    "lint_catalog",
    "load_catalog",
    "matches_excluded",
]
