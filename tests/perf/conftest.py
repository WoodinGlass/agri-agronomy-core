"""Session fixtures for perf tests (M9 PR-B).

Generating a 10k-taxa pack and building its SQLite once per session
keeps the four perf tests fast after the initial ~30 s setup. The
fixture is session-scoped; individual tests do not regenerate or rebuild.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ``tests/perf`` is not a package (no __init__.py); add its directory to
# sys.path so _gen_pack can be imported as a plain module.
sys.path.insert(0, str(Path(__file__).parent))
from _gen_pack import generate_perf_pack


@pytest.fixture(scope="session")
def perf_pack(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Generate + build a 10k-taxa pack once per session.

    Returns ``(source_dir, built_dir)``. Generation takes ~4 s, build
    takes ~20 s; after that every perf test reuses the same directories.
    """
    tmp = tmp_path_factory.mktemp("perf_pack")
    src = tmp / "source"
    built = tmp / "built"
    built.mkdir(parents=True)

    generate_perf_pack(src, n_taxa=10_000)

    r = subprocess.run(
        ["agri-core", "pack", "build", "--pack", str(src), "--out", str(built)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        pytest.fail(
            f"agri-core pack build failed (rc={r.returncode}):\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return src, built


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip perf tests when coverage tracing is active.

    ``coverage.py`` traces every executed line. Under perf tests the trace
    hook dominates the measured cost (~4x per call), so timing on a
    coverage-instrumented run says nothing about production performance.

    CI's ``perf`` job runs ``pytest -m perf --no-cov``; this hook makes
    that environment mandatory for anyone invoking perf tests locally.
    Without it, a plain ``pytest`` (which enables ``--cov`` via
    ``pyproject.toml`` ``addopts``) would fail every tight perf budget
    for a reason unrelated to the code under test.
    """
    from coverage import Coverage

    if Coverage.current() is None:
        return
    skip = pytest.mark.skip(
        reason=(
            "perf tests require --no-cov; coverage tracing inflates timing "
            "~4x. Run: pytest -m perf --no-cov"
        )
    )
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip)
