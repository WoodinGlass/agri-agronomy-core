"""Pack-loading errors with stable codes."""

from __future__ import annotations


class PackError(Exception):
    """Base class for pack-loading failures."""

    code: str = "PACK_ERROR"


class PackNotFoundError(PackError):
    code = "PACK_NOT_FOUND"


class InvalidPackError(PackError):
    code = "PACK_INVALID"


class UnsupportedSchemaVersionError(PackError):
    code = "PACK_SCHEMA_UNSUPPORTED"


class EngineTooOldError(PackError):
    code = "PACK_ENGINE_TOO_OLD"
