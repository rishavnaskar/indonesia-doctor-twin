"""Where a run persists.

Two backends behind one object. Postgres when a database is reachable, three
append-only JSONL files when it is not, and `backend` says which was chosen —
silently degrading to files would make "did that signature persist" a question
nobody thought to ask.

The fallback is not a convenience. About one facility in twelve lacks 24-hour
power and one in five has unreliable connectivity, so a clinical system that
refuses to start without a database is a clinical system that does not start.
Files also remain the right weight for a laptop: readable with `cat`, copied
with `scp`, diffed in a review.

What the database adds, and the reason it is preferred where it exists:

  * an audit log the application itself cannot rewrite — the migration installs
    a trigger that raises on UPDATE and DELETE
  * two clinicians on one deployment, without interleaved writes to one file
  * "which encounters are still unsent" as a statement rather than a scan

Both satisfy the same three interfaces, and the conformance suite runs against
both. That is what makes the choice an implementation detail rather than a
fork in the system's behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

def default_dir() -> Path:
    """Where the file backend writes, read on each call rather than at import.

    A module-level constant here silently ignored any `CLINICIAN_STORE` set
    after this module was first imported, which in a test suite is all of them:
    every test that pointed the store at its own temporary directory quietly
    shared one instead, and a test asserting a fresh store found the previous
    test's encounters in it.
    """
    return Path(os.environ.get("CLINICIAN_STORE", ".store"))

def forced_fresh() -> bool:
    """CLINICIAN_FRESH=1 re-runs work even when a stored result matches.

    Lives here rather than in either caller because both the clinician surface
    and the live runner honour it, and a convention implemented twice is a
    convention that drifts.
    """
    return os.environ.get("CLINICIAN_FRESH", "").lower() in ("1", "true", "yes")


def _forced_to_files() -> bool:
    """CLINICIAN_STORE_BACKEND=files stays on disk with a database running.

    Read on each call rather than once at import, because the test suite sets it
    in conftest and a module-level constant would depend on import order. The
    suite sets it so that a developer with a container up and a developer
    without one run the same tests — and, more to the point, so that no test can
    write into a real deployment's tables by accident.
    """
    return os.environ.get("CLINICIAN_STORE_BACKEND", "").lower() == "files"


class Store:
    """The durable side of one deployment."""

    def __init__(self, directory: Path | str | None = None, *, connection=None):
        self.dir = Path(directory or default_dir())
        self._conn = connection
        if self._conn is None and not _forced_to_files():
            from service import db

            self._conn = db.connect()
            if self._conn is not None:
                db.migrate(self._conn)

    @property
    def backend(self) -> str:
        return "postgres" if self._conn is not None else "files"

    # --------------------------------------------------------------- on disk

    @property
    def checkpoints(self) -> Path:
        return self.dir / "checkpoints.jsonl"

    @property
    def audit(self) -> Path:
        return self.dir / "audit.jsonl"

    @property
    def queue(self) -> Path:
        return self.dir / "outbound.jsonl"

    # -------------------------------------------------------------- backends

    def runtime(self):
        if self._conn is not None:
            from service.db import PostgresRuntime

            return PostgresRuntime(conn=self._conn)
        from service.graph.runtime import FileRuntime

        return FileRuntime(path=self.checkpoints)

    def audit_log(self):
        if self._conn is not None:
            from service.db import PostgresAuditLog

            return PostgresAuditLog(conn=self._conn)
        from service.signing import AuditLog

        return AuditLog(path=self.audit)

    def outbound(self):
        if self._conn is not None:
            from service.db import PostgresQueue

            return PostgresQueue(conn=self._conn)
        from service.emit.queue import OutboundQueue

        return OutboundQueue(self.queue)

    # ---------------------------------------------------------------- facts

    def summary(self) -> dict:
        runtime, log, queue = self.runtime(), self.audit_log(), self.outbound()
        # Only the file backend can have damaged lines: a truncated final line
        # is what a power cut leaves in a JSONL file, and is precisely the class
        # of problem a transactional write does not have.
        damaged = sum(len(getattr(o, "damaged", []) or []) for o in (runtime, log, queue))
        return {
            "backend": self.backend,
            "location": self._location(),
            "encounters_checkpointed": len(runtime.threads()),
            "signatures": len(log.records),
            "queued": len(queue.pending()),
            "sent": len(queue) - len(queue.pending()),
            "damaged_lines": damaged,
        }

    def reset(self) -> dict:
        """Destroy everything this store holds. Returns what was destroyed.

        Both backends, because a developer on files should not have to learn a
        different command from one on Postgres — the whole point of the two
        backends satisfying one interface is that the difference does not
        surface.
        """
        if self._conn is not None:
            from service.db import reset

            return {"backend": "postgres", "location": self._location(),
                    **reset(self._conn)}

        counts = {"backend": "files", "location": str(self.dir)}
        for name, path in (("checkpoints", self.checkpoints),
                           ("signatures", self.audit), ("outbound", self.queue)):
            counts[name] = (
                sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
                if path.exists() else 0
            )
            path.unlink(missing_ok=True)
        return counts

    def _location(self) -> str:
        if self._conn is None:
            return str(self.dir)
        from service.db import dsn

        # The password is in the environment, not in anything we print.
        url = dsn()
        return url.split("@")[-1] if "@" in url else url
