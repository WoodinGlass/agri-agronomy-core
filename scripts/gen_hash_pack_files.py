#!/usr/bin/env python3
"""Regenerate tests/vectors/hash_pack_files.json from the Python oracle.

The Python `hash_pack_files` is the reference; the Rust port must match
byte-for-byte. Run:

    python scripts/gen_hash_pack_files.py

Deterministic, offline, no Node.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from agri_core.pack.verify import hash_pack_files  # noqa: E402

OUT = REPO / "tests" / "vectors" / "hash_pack_files.json"


def _b64(d: dict[str, bytes]) -> dict[str, str]:
    return {k: base64.b64encode(v).decode("ascii") for k, v in d.items()}


MINIMAL_TOML = (
    b'name = "minimal"\n'
    b'version = "1.0.0"\n'
    b"schema_version = 1\n"
    b'engine_min = "0.0.0"\n'
    b'dictionary_min = "1.0.0"\n'
)

SOURCES_HDR = b"id,url,license,commercial_use,access_date,citation\n"


def cases() -> list[dict]:
    cases: list[dict] = []

    def add(name: str, files: dict[str, bytes], hash_alg: str) -> None:
        expected = hash_pack_files(files, hash_alg=hash_alg)
        cases.append(
            {
                "name": name,
                "files_b64": _b64(files),
                "hash_alg": hash_alg,
                "expected": expected,
            }
        )

    # Minimal pack, both algs
    minimal = {"pack.toml": MINIMAL_TOML, "sources.csv": SOURCES_HDR}
    add("minimal_pre", minimal, "pre-rfc8785")
    add("minimal_rfc", minimal, "rfc8785")

    # Pack.toml with hash_alg declared (must be stripped)
    with_alg = dict(minimal)
    with_alg["pack.toml"] = MINIMAL_TOML + b'hash_alg = "rfc8785"\n'
    add("with_alg_field_pre", with_alg, "pre-rfc8785")
    add("with_alg_field_rfc", with_alg, "rfc8785")

    # Key order invariance
    reordered = dict(minimal)
    reordered["pack.toml"] = (
        b'engine_min = "0.0.0"\n'
        b"schema_version = 1\n"
        b'dictionary_min = "1.0.0"\n'
        b'version = "1.0.0"\n'
        b'name = "minimal"\n'
    )
    add("key_order_pre", reordered, "pre-rfc8785")
    add("key_order_rfc", reordered, "rfc8785")

    # CRLF in non-toml files
    crlf = dict(minimal)
    crlf["sources.csv"] = SOURCES_HDR.replace(b"\n", b"\r\n")
    add("crlf_pre", crlf, "pre-rfc8785")
    add("crlf_rfc", crlf, "rfc8785")

    # Bare CR
    bare = dict(minimal)
    bare["sources.csv"] = b"a\rb\r"
    add("bare_cr_pre", bare, "pre-rfc8785")

    # Trailing content_hash
    with_ch = dict(minimal)
    with_ch["pack.toml"] = MINIMAL_TOML + b'content_hash = "sha256:' + b"0" * 64 + b'"\n'
    add("with_content_hash_pre", with_ch, "pre-rfc8785")
    add("with_content_hash_rfc", with_ch, "rfc8785")

    # Unicode in pack.toml
    uni = dict(minimal)
    uni["pack.toml"] = MINIMAL_TOML.replace(b"minimal", "café".encode())
    add("unicode_pre", uni, "pre-rfc8785")
    add("unicode_rfc", uni, "rfc8785")

    # Sample pack
    sample = REPO / "src" / "agri_core" / "_samples" / "sample_pack"
    from agri_core.pack.files import read_pack_bytes

    sample_files = dict(read_pack_bytes(sample))
    add("sample_pre", sample_files, "pre-rfc8785")
    add("sample_rfc", sample_files, "rfc8785")

    return cases


def main() -> int:
    cs = cases()
    OUT.write_text(json.dumps(cs, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({len(cs)} cases, {OUT.stat().st_size} bytes)")
    for c in cs:
        print(f"  {c['name']}: {c['expected'][:26]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
