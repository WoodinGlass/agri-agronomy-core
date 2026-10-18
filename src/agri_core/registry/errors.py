"""Exceptions raised by the registry."""

from __future__ import annotations


class DataNotFoundError(FileNotFoundError):
    """Raised when profile data or JSON schemas cannot be located or are incomplete."""
