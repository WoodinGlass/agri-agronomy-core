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
