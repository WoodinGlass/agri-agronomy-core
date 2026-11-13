"""Type stubs for the native Rust kernel. Checked by `mypy stubtest`."""
from __future__ import annotations
from typing import Any

__version__: str

def canonical_json(obj: Any) -> bytes: ...
def sha256_hex(data: bytes) -> str: ...
def compute_request_id(
    subject: Any | None,
    inputs: Any,
    engine_version: str,
    pack_hash: str | None = ...,
) -> str: ...
