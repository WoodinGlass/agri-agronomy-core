"""Perf gate: native diff vs Python diff on the 10k reference pack.

ADR-019 Phase E, HP#9 (three variants) and N15 (RSS subprocess, not
tracemalloc).

Three variants, all on the same 10k pack (perf_pack fixture):
- self-diff:    pack vs itself; identical=True.
- mutated-1pct: 1% of fact values flipped in place; identical=False.
- added-removed: 0.1% fact deletion + 0.1% fresh insert; identical=False.

Concurrency note (KOREKSI vs PREVIEW E.5 awal): every measurement runs
in an isolated subprocess. VmHWM is a *peak-since-process-start* metric
with no reset; running two variants in one process would attribute the
larger variant's peak to the smaller one. Subprocess isolation is the
only reliable way to get per-variant RSS. Startup (~2 s python import)
is identical for both backends, so the time ratio stays valid.

Asserts per variant:
- identical flag matches between Python and native (parity, not only perf).
- native_ms .json but not
asserted; gap is M21.5 follow-up (PyO3 render dominates at 320k entries).

Skip guard: exp-diff feature off in wheel (N18). PR runs skip cleanly.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_TESTS_PERF_DIR = Path(__file__).resolve().parent
if str(_TESTS_PERF_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_PERF_DIR))

try:
    from agri_core import _native

    _NATIVE_AVAILABLE = hasattr(_native, "diff_pack_paths")
except ImportError:
    _native = None
    _NATIVE_AVAILABLE = False

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(
        not _NATIVE_AVAILABLE,
        reason="exp-diff feature off (rebuild with --features exp-diff)",
    ),
]

_MUT1_ROWS = 3200  # about 1% of 320k facts
_ARD_ROWS = 320  # 0.1% per side
_BENCH_DIR_ENV = "AGRI_BENCH_DIR"
_BENCH_DIR_DEFAULT = "/tmp/agri-bench"


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _patch_artifact_sha256(dir_path: Path) -> None:
    toml_p = dir_path / "pack.toml"
    new_sha = _sha256(dir_path / "pack.sqlite")
    lines = []
    for ln in toml_p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("artifact_sha256"):
            lines.append('artifact_sha256 = "' + new_sha + '"')
        else:
            lines.append(ln)
    toml_p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clone_dir(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy(src / "pack.sqlite", dst / "pack.sqlite")
    shutil.copy(src / "pack.toml", dst / "pack.toml")


def _make_mut1(built: Path, mut_dir: Path) -> None:
    _clone_dir(built, mut_dir)
    conn = sqlite3.connect(str(mut_dir / "pack.sqlite"))
    try:
        cur = conn.cursor()
        cur.execute("SELECT fact_id FROM facts ORDER BY fact_id LIMIT ?", (_MUT1_ROWS,))
        ids = [row[0] for row in cur.fetchall()]
        cur.executemany(
            "UPDATE facts SET value = ? WHERE fact_id = ?",
            [('{"shape":"scalar","unit":"degree_Celsius","value":99.0}', fid) for fid in ids],
        )
        conn.commit()
    finally:
        conn.close()
    _patch_artifact_sha256(mut_dir)


def _make_ard(built: Path, ard_dir: Path) -> None:
    _clone_dir(built, ard_dir)
    conn = sqlite3.connect(str(ard_dir / "pack.sqlite"))
    try:
        cur = conn.cursor()
        cur.execute("SELECT fact_id FROM facts ORDER BY fact_id LIMIT ?", (_ARD_ROWS,))
        del_ids = [row[0] for row in cur.fetchall()]
        cur.executemany("DELETE FROM facts WHERE fact_id = ?", [(fid,) for fid in del_ids])
        cur.execute(
            "SELECT taxon_id, parameter, phase, value, scope, provenance_kind, src, "
            "dataset_id, locator, evidence, status, reviewed_by, reviewed_at, superseded_by "
            "FROM facts ORDER BY fact_id LIMIT ?",
            (_ARD_ROWS,),
        )
        rows = cur.fetchall()
        cur.executemany(
            "INSERT INTO facts (fact_id, taxon_id, parameter, phase, value, scope, "
            "provenance_kind, src, dataset_id, locator, evidence, status, "
            "reviewed_by, reviewed_at, superseded_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(f"F9{i:011d}", *tuple(row)) for i, row in enumerate(rows)],
        )
        conn.commit()
    finally:
        conn.close()
    _patch_artifact_sha256(ard_dir)


@pytest.fixture(scope="session")
def diff_perf_variants(
    perf_pack: tuple[Path, Path],
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    _src, built = perf_pack
    base = tmp_path_factory.mktemp("diff_perf")
    mut1 = base / "mut1"
    ard = base / "ard"
    _make_mut1(built, mut1)
    _make_ard(built, ard)
    return {"self": built, "mut1": mut1, "ard": ard}


_RUNNER_TEMPLATE = r"""
import json, sys, time
from pathlib import Path

def vmhwm():
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("VmHWM:"):
                    return int(ln.split()[1])
    except Exception:
        return -1
    return -1

mode = sys.argv[1]
old_p = Path(sys.argv[2])
new_p = Path(sys.argv[3])

if mode == "py":
    from agri_core.pack import load_knowledge_set
    from agri_core.pack.diff import diff_packs

    t0 = time.perf_counter()
    a = load_knowledge_set(old_p, allow_synthetic=True)
    b = load_knowledge_set(new_p, allow_synthetic=True)
    r = diff_packs(a, b)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    identical = bool(r.identical)
elif mode == "native":
    from agri_core.pack.diff import diff_pack_paths
    from agri_core.pack.loader import parse_manifest_bytes

    om = parse_manifest_bytes((old_p / "pack.toml").read_bytes())
    nm = parse_manifest_bytes((new_p / "pack.toml").read_bytes())
    t0 = time.perf_counter()
    r = diff_pack_paths(old_p, new_p, old_manifest=om, new_manifest=nm)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    identical = bool(r.identical)
else:
    raise SystemExit("unknown mode " + mode)

print(json.dumps({"elapsed_ms": elapsed_ms, "identical": identical, "vmhwm_kb": vmhwm()}))
"""


def _run_child(mode: str, old_p: Path, new_p: Path) -> tuple[int, int, bool]:
    args = [sys.executable, "-c", _RUNNER_TEMPLATE, mode, str(old_p), str(new_p)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("child failed for " + mode + ": " + r.stderr[-2000:])
    last = r.stdout.strip().splitlines()[-1]
    data = json.loads(last)
    return int(data["elapsed_ms"]), int(data["vmhwm_kb"]), bool(data["identical"])


def _measure_pair(old_p: Path, new_p: Path) -> dict[str, Any]:
    py_ms, py_rss, py_identical = _run_child("py", old_p, new_p)
    nt_ms, nt_rss, nt_identical = _run_child("native", old_p, new_p)
    assert py_identical == nt_identical, (
        "parity failure: py=" + str(py_identical) + " native=" + str(nt_identical)
    )
    return {
        "py_ms": py_ms,
        "py_rss": py_rss,
        "nt_ms": nt_ms,
        "nt_rss": nt_rss,
        "identical": py_identical,
    }


def _write_bench(label: str, m: dict[str, Any]) -> None:
    out_dir = Path(os.environ.get(_BENCH_DIR_ENV, _BENCH_DIR_DEFAULT))
    out_dir.mkdir(parents=True, exist_ok=True)
    t_ratio = round(m["nt_ms"] / m["py_ms"], 4) if m["py_ms"] else None
    r_ratio = round(m["nt_rss"] / m["py_rss"], 4) if m["py_rss"] else None
    payload = {
        "variant": label,
        "python_ms": m["py_ms"],
        "native_ms": m["nt_ms"],
        "time_ratio": t_ratio,
        "python_vmhwm_kb": m["py_rss"],
        "native_vmhwm_kb": m["nt_rss"],
        "rss_ratio": r_ratio,
        "identical": m["identical"],
        "measured_at": int(time.time()),
        "platform": sys.platform,
        "cpu_count": os.cpu_count(),
    }
    (out_dir / ("bench-" + label + ".json")).write_text(
        json.dumps(payload, indent=2) + chr(10), encoding="utf-8"
    )
    print()
    print("  " + label + ":")
    print("    python: " + str(m["py_ms"]) + " ms  VmHWM=" + str(m["py_rss"]) + " kB")
    print("    native: " + str(m["nt_ms"]) + " ms  VmHWM=" + str(m["nt_rss"]) + " kB")
    print(
        "    time_ratio="
        + str(t_ratio)
        + "  rss_ratio="
        + str(r_ratio)
        + "  identical="
        + str(m["identical"])
    )


def _assert_gates(label: str, m: dict[str, Any]) -> None:
    assert m["nt_ms"] <= 0.5 * m["py_ms"], (
        label
        + ": native "
        + str(m["nt_ms"])
        + " ms "
        + "vs python "
        + str(m["py_ms"])
        + " ms (gate <=0.5x, ADR-019 floor)"
    )
    assert m["nt_rss"] <= 2.0 * m["py_rss"], (
        label
        + ": native VmHWM "
        + str(m["nt_rss"])
        + " kB "
        + "vs python "
        + str(m["py_rss"])
        + " kB (gate <=2x, N15)"
    )


def test_self_diff(diff_perf_variants: dict[str, Path]) -> None:
    built = diff_perf_variants["self"]
    m = _measure_pair(built, built)
    assert m["identical"] is True
    _write_bench("self", m)
    _assert_gates("self", m)


def test_mutated_1pct(diff_perf_variants: dict[str, Path]) -> None:
    old = diff_perf_variants["self"]
    new = diff_perf_variants["mut1"]
    m = _measure_pair(old, new)
    assert m["identical"] is False
    _write_bench("mut1", m)
    _assert_gates("mut1", m)


def test_added_removed(diff_perf_variants: dict[str, Path]) -> None:
    old = diff_perf_variants["self"]
    new = diff_perf_variants["ard"]
    m = _measure_pair(old, new)
    assert m["identical"] is False
    _write_bench("ard", m)
    _assert_gates("ard", m)
