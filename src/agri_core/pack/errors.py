"""Pack-loading errors with stable codes."""

from __future__ import annotations


class PackError(Exception):
    """Base class for pack-loading failures.

    Every subclass carries a stable ``code``. The optional ``file``,
    ``line`` and ``key`` attributes identify where a failure happened
    inside a pack. ``findings`` holds additional ``PackError`` instances
    (up to 20 per K4) when a batch check collects more than one problem;
    ``str(self)`` reflects only the first finding.
    """

    code: str = "PACK_ERROR"

    def __init__(
        self,
        message: str = "",
        *,
        file: str | None = None,
        line: int | None = None,
        key: str | None = None,
        findings: tuple[PackError, ...] = (),
    ) -> None:
        super().__init__(message)
        self.file = file
        self.line = line
        self.key = key
        self.findings = findings


class PackNotFoundError(PackError):
    code = "PACK_NOT_FOUND"


class InvalidPackError(PackError):
    code = "PACK_INVALID"


class UnsupportedSchemaVersionError(PackError):
    code = "PACK_SCHEMA_UNSUPPORTED"


class EngineTooOldError(PackError):
    code = "PACK_ENGINE_TOO_OLD"


class PackTableInvalidError(PackError):
    code = "PACK_TABLE_INVALID"


class PackDuplicateKeyError(PackError):
    code = "PACK_DUPLICATE_KEY"


class PackFKViolationError(PackError):
    code = "PACK_FK_VIOLATION"


class PackUnknownParameterError(PackError):
    code = "PACK_UNKNOWN_PARAMETER"


class PackShapeMismatchError(PackError):
    code = "PACK_SHAPE_MISMATCH"


class PackPhaseInvalidError(PackError):
    code = "PACK_PHASE_INVALID"


class PackScopeInvalidError(PackError):
    code = "PACK_SCOPE_INVALID"


class PackHashMismatchError(PackError):
    code = "PACK_HASH_MISMATCH"


class PackTooLargeError(PackError):
    code = "PACK_TOO_LARGE"


class PackFeatureUnsupportedError(PackError):
    code = "PACK_FEATURE_UNSUPPORTED"


class PackDictionaryIncompatibleError(PackError):
    code = "PACK_DICTIONARY_INCOMPATIBLE"


class PackSyntheticNotAllowedError(PackError):
    code = "PACK_SYNTHETIC_NOT_ALLOWED"


class PackValueOutOfRangeError(PackError):
    code = "PACK_VALUE_OUT_OF_RANGE"


class PackEnumInvalidError(PackError):
    code = "PACK_ENUM_INVALID"


class PackUnitMismatchError(PackError):
    code = "PACK_UNIT_MISMATCH"


class PackSafetyViolationError(PackError):
    code = "PACK_SAFETY_VIOLATION"
