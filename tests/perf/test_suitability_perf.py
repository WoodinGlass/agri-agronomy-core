"""Perf gate: batch_suitability 5000 taxa.

Per Q7 (M15): measure actual, do not claim a budget. The only assertion
is a catastrophic-regression guard (< 5000 ms). The real budget is
calibrated at P10 once this number is on record.
"""

from __future__ import annotations

import statistics
import time
from datetime import date
from pathlib import Path

import pytest

from agri_core.models import FactRow, ScalarValue, TaxonRow, TrapezoidValue
from agri_core.models.dictionary import Dictionary
from agri_core.pack.knowledge_set import InMemoryKnowledgeSet
from agri_core.pack.manifest import PackManifest
from agri_core.suitability import Site, batch_suitability

pytestmark = pytest.mark.perf

_REPO = Path(__file__).resolve().parents[2]
_DICT = Dictionary.load(_REPO / "dictionary" / "parameters.core.yaml")
_SITE_PARAMS = ("soil_ph", "soil_ec", "air_temp_day", "air_temp_night", "air_rh", "vpd", "dli")
_PHASE_BEARING = {"air_temp_day", "air_temp_night", "air_rh", "vpd", "dli"}
_PTS = (4.5, 6.0, 7.0, 8.5)
_N_TAXA = 5000
_N_RUNS = 3

_FID_COUNTER = [0]


def _next_fid() -> str:
    _FID_COUNTER[0] += 1
    return f"F{_FID_COUNTER[0]:011d}"


def _build_pack() -> InMemoryKnowledgeSet:
    manifest = PackManifest.model_validate(
        {
            "name": "perf",
            "version": "1.0.0",
            "schema_version": 1,
            "engine_min": "0.0.0",
            "dictionary_min": "1.0.0",
        }
    )
    taxa = [
        TaxonRow(
            taxon_id=f"T{i:09d}",
            rank="species",
            scientific_name=f"Testus {i}",
            organism_group="vascular_plant",
            archetype="annual",
            uses=["vegetable"],
            traits=[],
            src=["S001"],
        )
        for i in range(_N_TAXA)
    ]
    facts = []
    for i in range(_N_TAXA):
        tid = f"T{i:09d}"
        for p in _SITE_PARAMS:
            ph = "flowering" if p in _PHASE_BEARING else None
            facts.append(
                FactRow(
                    fact_id=_next_fid(),
                    taxon_id=tid,
                    parameter=p,
                    phase=ph,
                    value=TrapezoidValue(shape="trapezoid", unit="x", pts=_PTS),
                    scope={},
                    provenance_kind="curated",
                    src=["S001"],
                    locator="t",
                    evidence="B",
                    status="approved",
                    reviewed_by="r",
                    reviewed_at=date(2026, 1, 1),
                )
            )
        for p in _SITE_PARAMS:
            facts.append(
                FactRow(
                    fact_id=_next_fid(),
                    taxon_id=tid,
                    parameter=f"suitability_weight_{p}",
                    phase=None,
                    value=ScalarValue(shape="scalar", unit="dimensionless", value=1.0),
                    scope={},
                    provenance_kind="curated",
                    src=["S001"],
                    locator="t",
                    evidence="B",
                    status="approved",
                    reviewed_by="r",
                    reviewed_at=date(2026, 1, 1),
                )
            )
    return InMemoryKnowledgeSet.from_rows(
        manifest=manifest,
        pack_hash="sha256:" + "1" * 64,
        dictionary_version=_DICT.version,
        dictionary=_DICT,
        verified=True,
        taxa=taxa,
        facts=facts,
    )


@pytest.fixture(scope="module")
def perf_pack_5000() -> tuple[InMemoryKnowledgeSet, list[str], Site]:
    pack = _build_pack()
    ids = [f"T{i:09d}" for i in range(_N_TAXA)]
    site = Site(**{p: 6.5 for p in _SITE_PARAMS})
    return pack, ids, site


def test_batch_5000_actual(perf_pack_5000) -> None:
    pack, ids, site = perf_pack_5000
    # warmup
    batch_suitability(pack, site, ids[:100], phase="flowering")

    times_ms: list[float] = []
    for _ in range(_N_RUNS):
        t0 = time.perf_counter()
        batch_suitability(pack, site, ids, phase="flowering")
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    best = min(times_ms)
    med = statistics.median(times_ms)
    worst = max(times_ms)
    print(
        f"\n  batch_suitability n={_N_TAXA}: "
        f"min={best:.1f} ms  median={med:.1f} ms  max={worst:.1f} ms"
    )
    # Q7: only catastrophic-regression guard.
    assert best < 5000.0, f"batch 5000 took {best:.1f} ms (catastrophic regression)"
