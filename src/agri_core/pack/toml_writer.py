"""Minimal deterministic TOML serializer for built pack manifests."""

from __future__ import annotations

from agri_core.pack.manifest import PackManifest


def _toml_str(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return _toml_str(v)
    raise TypeError(f"unsupported type for TOML: {type(v).__name__}")


def dump_manifest(manifest: PackManifest) -> bytes:
    """Serialize a PackManifest to canonical TOML bytes.

    Iterates PackManifest.model_fields so a new manifest field cannot be
    silently dropped. None-valued fields are omitted. LF line endings,
    trailing LF. Key order follows model_fields declaration order.
    """
    lines: list[str] = []
    for name in PackManifest.model_fields:
        value = getattr(manifest, name)
        if value is None:
            continue
        lines.append(f"{name} = {_toml_value(value)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


__all__ = ["dump_manifest"]
