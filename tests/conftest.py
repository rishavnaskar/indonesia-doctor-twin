"""Suite-wide defaults.

The store prefers Postgres whenever one is reachable, which is right for a
deployment and wrong for a test run: a developer with the container up would
otherwise have every durability test writing into the same tables a real
deployment uses, and `Store(tmp_path)` would quietly ignore the temporary
directory it was handed.

So the suite pins the file backend. The Postgres tests do not go through
`Store` — they connect directly, into a schema created for the test and dropped
afterwards — so they are unaffected by this and still run.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("CLINICIAN_STORE_BACKEND", "files")

# ... and into a throwaway directory. The demo surface persists every encounter
# it runs, and its tests run nine of them, so an unpinned store put half a
# megabyte of checkpoints into the working tree on each `make`.
os.environ.setdefault("CLINICIAN_STORE", tempfile.mkdtemp(prefix="clinician-test-"))
