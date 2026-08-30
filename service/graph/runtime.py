"""The durable workflow runtime, behind an interface.

BUILD.md picks LangGraph as a library, and that choice still stands: the
interrupt/resume model *is* our signature line, checkpointers are our offline
story, and time-travel replay is our audit story. Rebuilding those is months of
work done worse.

What we do not want is that choice spreading. Everything the system needs from a
workflow engine is four verbs, declared here:

    run      - advance a workflow to its next pause or its end
    interrupt- pause before an irreversible action and persist the state
    resume   - continue from a checkpoint, given a human decision
    replay   - reconstruct exactly what the system saw at a past step

/service/graph is the only module permitted to import an orchestration library
(enforced in tools/ci_checks.py). Everything else depends on this interface, so
swapping engines is one module's work rather than a rewrite.

The in-memory implementation below is the reference the durable backend must
match. It makes the interrupt semantics testable with no service running, which
is what a conformance suite for a persistent checkpointer needs to exist
against.

Data residency, restated because it is a compliance landmine rather than a
preference: self-hosted only. No hosted control plane, no SaaS tracing backend.
Tracing is enabled by default in many setups and would quietly ship patient data
offshore.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Protocol


class Interrupted(Exception):
    """Raised when a workflow pauses for a human decision."""

    def __init__(self, thread_id: str, payload: Any):
        super().__init__(f"workflow {thread_id} awaiting a human decision")
        self.thread_id = thread_id
        self.payload = payload


@dataclass
class Checkpoint:
    thread_id: str
    step: str
    state: Any
    sequence: int


class DurableRuntime(Protocol):
    def start(self, thread_id: str, state: Any) -> None: ...
    def checkpoint(self, thread_id: str, step: str, state: Any) -> Checkpoint: ...
    def interrupt(self, thread_id: str, payload: Any) -> None: ...
    def resume(self, thread_id: str, decision: Any) -> Any: ...
    def replay(self, thread_id: str, sequence: int) -> Checkpoint: ...


@dataclass
class InMemoryRuntime:
    """Reference implementation. Correct semantics, no durability."""

    checkpoints: dict[str, list[Checkpoint]] = field(default_factory=dict)
    pending: dict[str, Any] = field(default_factory=dict)

    def start(self, thread_id: str, state: Any) -> None:
        self.checkpoints[thread_id] = []
        self.checkpoint(thread_id, "start", state)

    def checkpoint(self, thread_id: str, step: str, state: Any) -> Checkpoint:
        history = self.checkpoints.setdefault(thread_id, [])
        # Deep copy so replay reconstructs what the system saw, not what the
        # state later became. An audit trail of live references is not one.
        entry = Checkpoint(thread_id, step, copy.deepcopy(state), len(history))
        history.append(entry)
        return entry

    def interrupt(self, thread_id: str, payload: Any) -> None:
        self.pending[thread_id] = payload
        raise Interrupted(thread_id, payload)

    def resume(self, thread_id: str, decision: Any) -> Any:
        if thread_id not in self.pending:
            raise KeyError(f"no interrupt pending for {thread_id}")
        payload = self.pending.pop(thread_id)
        self.checkpoint(thread_id, "resumed", {"decision": decision})
        return payload

    def replay(self, thread_id: str, sequence: int) -> Checkpoint:
        return self.checkpoints[thread_id][sequence]


@dataclass
class FileRuntime(InMemoryRuntime):
    """The same semantics, surviving a restart.

    BUILD.md says a checkpoint is a recovery point for interruption, timeout,
    human handoff and *service restart*, and that replay is how a regulator is
    answered when they ask why the system said something. Neither was true of a
    runtime that kept everything in a dictionary: about one facility in twelve
    lacks 24-hour power, so "the process died" is the ordinary case rather than
    the exotic one, and an audit trail that does not outlive the process is not
    an audit trail.

    Append-only JSONL, the same shape the outbound queue already uses and for
    the same reasons: a partial final line from a power cut is skipped rather
    than fatal, and later entries win on replay. Deliberately not a database —
    a file that can be read with `cat`, copied, and diffed is the right weight
    for a prototype, and the contract in this module is what a Postgres or
    LangGraph backend would implement instead.
    """

    path: Path | None = None
    damaged: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path is not None and Path(self.path).exists():
            self._load()

    def start(self, thread_id: str, state: Any) -> None:
        # Never clears history: a restarted encounter must not erase what the
        # system saw before it fell over.
        self.checkpoints.setdefault(thread_id, [])
        self.checkpoint(thread_id, "start", state)

    def checkpoint(self, thread_id: str, step: str, state: Any) -> Checkpoint:
        entry = super().checkpoint(thread_id, step, state)
        self._append(entry)
        return entry

    def threads(self) -> list[str]:
        return sorted(self.checkpoints)

    def _append(self, entry: Checkpoint) -> None:
        if self.path is None:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "thread_id": entry.thread_id,
                "step": entry.step,
                "sequence": entry.sequence,
                "state": entry.state,
            }, default=str) + "\n")

    def _load(self) -> None:
        for line in Path(self.path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                entry = Checkpoint(row["thread_id"], row["step"],
                                   row["state"], row["sequence"])
            except (json.JSONDecodeError, KeyError, TypeError):
                # A truncated final line is what a power cut leaves behind.
                # Losing every checkpoint behind it would defeat the point.
                self.damaged.append(line[:200])
                continue
            history = self.checkpoints.setdefault(entry.thread_id, [])
            if entry.sequence < len(history):
                history[entry.sequence] = entry
            else:
                history.append(entry)
