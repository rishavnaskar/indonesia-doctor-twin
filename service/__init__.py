"""The engine: pack loading, intake, reconciliation, reasoning, gate, emit.

Nothing in here names a country, a payer, a drug or a guideline. Those live in
/packs and are checked for by tools/ci_checks.py.
"""

from __future__ import annotations

# Single source of truth for the version. pyproject.toml carries the same
# string, and tests/test_version.py fails if the two drift.
__version__ = "0.2.0"
