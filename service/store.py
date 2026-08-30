"""Where a run persists.

Three append-only JSONL files under one directory: the checkpoints, the
signature log, and the outbound queue. Deliberately not a database — a file
that can be read with `cat`, copied off a machine and diffed is the right
weight for a prototype, and every one of them is behind an interface a
Postgres or LangGraph backend would implement instead.

They are separate files because they answer different questions and have
different lifetimes. The queue is drained and its items become sent; the audit
log is never drained, because a signature is not a task.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("CLINICIAN_STORE", ".store"))


class Store:
    """The durable side of one deployment."""

    def __init__(self, directory: Path | str | None = None):
        self.dir = Path(directory or DEFAULT_DIR)

    @property
    def checkpoints(self) -> Path:
        return self.dir / "checkpoints.jsonl"

    @property
    def audit(self) -> Path:
        return self.dir / "audit.jsonl"

    @property
    def queue(self) -> Path:
        return self.dir / "outbound.jsonl"

    def runtime(self):
        from service.graph.runtime import FileRuntime

        return FileRuntime(path=self.checkpoints)

    def audit_log(self):
        from service.signing import AuditLog

        return AuditLog(path=self.audit)

    def outbound(self):
        from service.emit.queue import OutboundQueue

        return OutboundQueue(self.queue)

    def summary(self) -> dict:
        from service.emit.queue import OutboundQueue

        runtime, log = self.runtime(), self.audit_log()
        queue = OutboundQueue(self.queue)
        return {
            "directory": str(self.dir),
            "encounters_checkpointed": len(runtime.threads()),
            "signatures": len(log.records),
            "queued": len(queue.pending()),
            "sent": len(queue) - len(queue.pending()),
            "damaged_lines": len(runtime.damaged) + len(log.damaged) + len(queue.damaged),
        }
