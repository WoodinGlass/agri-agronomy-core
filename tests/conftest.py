"""pytest configuration shared across test kinds."""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("ci", derandomize=True, deadline=None, max_examples=100)
settings.register_profile("default", derandomize=False, deadline=None, max_examples=50)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
