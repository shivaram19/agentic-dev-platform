"""
Agentic Development Platform - Test package.

This package provides the base layout for integration and unit tests.
It does not contain tests itself, but:

  - ensures the `tests` directory is treated as a Python package,
  - defines common test fixtures or helpers that can be reused across modules,
  - and can be imported by `conftest.py` or individual test files.

In a real project you would typically have:

  - `tests/unit/` for unit tests of core modules (agents, models, registry, etc.),
  - `tests/integration/` for tests that wire together MCP, LLM, and DB,
  - `tests/e2e/` for end‑to‑end CLI or IDE‑driven scenarios.

Here we keep it minimal so the platform still passes `python -m pytest` when
you add real test modules.
"""
from pathlib import Path
import os

# Expose a common project root for tests.
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
os.environ["PROJECT_ROOT"] = str(PROJECT_ROOT)

# If you want, you can add common fixtures here that will be auto‑imported
# by pytest when this package is imported.
def pytest_configure(config) -> None:
    """
    Optional: hook into pytest configuration.

    This is not used here, but can be added later to register plugins or
    tweak logging.
    """
    pass
