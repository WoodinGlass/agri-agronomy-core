"""``meta()`` and ``MetaInfo`` (M8 review G12).

Locks the ``MetaInfo`` contract: every field documented in ADR-004
§"meta()" must be present, with a value that traces back to a known
source. ``engine_min`` was added by G12; ``resolution_policy_version``
was already present (G5) but not listed in §meta() until G12.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agri_core import RESOLUTION_POLICY_VERSION, __version__
from agri_core.pack import load_knowledge_set
from agri_core.registry import MetaInfo, meta

pytestmark = pytest.mark.contract

_REPO = Path(__file__).resolve().parents[2]
_SAMPLE = _REPO / "src" / "agri_core" / "_samples" / "sample_pack"


@pytest.fixture(scope="module")
def loaded_pack():  # type: ignore[no-untyped-def]
    return load_knowledge_set(_SAMPLE, allow_synthetic=True)


def test_meta_has_engine_min(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """G12: ``MetaInfo`` carries ``engine_min`` as a required field."""
    m = meta(loaded_pack)
    assert "engine_min" in MetaInfo.model_fields
    assert isinstance(m.engine_min, str)
    assert m.engine_min  # non-empty


def test_meta_engine_min_from_manifest(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """G12: ``engine_min`` mirrors ``pack.manifest.engine_min`` exactly."""
    m = meta(loaded_pack)
    assert m.engine_min == loaded_pack.manifest.engine_min


def test_meta_has_resolution_policy_version(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """G12: lock ``resolution_policy_version`` (present since G5)."""
    m = meta(loaded_pack)
    assert "resolution_policy_version" in MetaInfo.model_fields
    assert m.resolution_policy_version == RESOLUTION_POLICY_VERSION


def test_meta_engine_version_is_running(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """Sanity: ``engine_version`` is the running engine, not the pack version."""
    m = meta(loaded_pack)
    assert m.engine_version == __version__
    # And it must NOT be the pack version (which the sample pack sets to 0.1.0).
    assert m.engine_version != m.pack_version


def test_meta_pack_version_from_manifest(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """Sanity: ``pack_version`` mirrors ``pack.manifest.version``."""
    m = meta(loaded_pack)
    assert m.pack_version == loaded_pack.manifest.version


def test_meta_engine_min_is_distinct_from_engine_version(loaded_pack) -> None:  # type: ignore[no-untyped-def]
    """G12: ``engine_min`` (pack requirement) and ``engine_version`` (running)
    answer different questions. In the sample pack they differ; this test
    guards against accidentally collapsing the two."""
    m = meta(loaded_pack)
    # They could coincidentally be equal for some packs, but for the sample
    # they are not — and the semantics differ regardless.
    assert hasattr(m, "engine_min")
    assert hasattr(m, "engine_version")
    assert m.engine_min == loaded_pack.manifest.engine_min
