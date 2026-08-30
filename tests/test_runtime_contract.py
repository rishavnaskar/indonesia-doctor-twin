"""The durable-runtime contract, as a suite every implementation must pass.

BUILD.md argues for putting an orchestration library behind this interface. No
such library is used today, and that is a deliberate position rather than an
omission: the interface is the commitment, the backend is not.

The point of this file is to stop that being an assertion. "Swapping the
backend is one module's work" is only true if there is a definition of what a
backend has to do, and these tests are it. Three implementations run against
them — in memory, append-only files, and Postgres — and they are the same
tests, not a suite per backend. A durable backend that quietly differs in
semantics is worse than no durable backend, because what runs in a clinic then
behaves unlike what ran in the test.

The Postgres parameter skips rather than fails when no database is listening.
That is not laziness about coverage: the database is optional by design, and a
suite that could not run without a container would contradict the thing it is
testing.
"""

from __future__ import annotations

import pytest

from service.graph.runtime import Checkpoint, InMemoryRuntime, Interrupted


def implementations():
    """Every runtime that claims to satisfy the contract."""
    return [InMemoryRuntime, _file_runtime_factory, _postgres_runtime_factory]


def _file_runtime_factory():
    import tempfile
    from pathlib import Path

    from service.graph.runtime import FileRuntime

    return FileRuntime(path=Path(tempfile.mkdtemp()) / "cp.jsonl"), None


_file_runtime_factory.__name__ = "FileRuntime"


def _postgres_runtime_factory():
    from service.db import PostgresRuntime
    from tests.pgfixture import connection

    conn = connection()
    if conn is None:
        pytest.skip("no database reachable — `docker compose up -d` to run this")
    return PostgresRuntime(conn=conn), conn


_postgres_runtime_factory.__name__ = "PostgresRuntime"


@pytest.fixture(params=implementations(), ids=lambda c: c.__name__)
def runtime(request):
    made = request.param()
    # InMemoryRuntime is a class; the others are factories returning a
    # (runtime, resource) pair. Normalising here keeps every test below
    # ignorant of which backend it is exercising, which is the point.
    instance, resource = made if isinstance(made, tuple) else (made, None)
    yield instance
    if resource is not None:
        from tests.pgfixture import drop

        drop(resource)


def test_a_thread_can_be_started_and_checkpointed(runtime):
    runtime.start("T1", {"step": 0})
    checkpoint = runtime.checkpoint("T1", "proposed", {"step": 1})
    assert isinstance(checkpoint, Checkpoint)


def test_checkpoints_are_ordered_and_replayable(runtime):
    """The audit story. When a regulator asks why the system said something, we
    replay the exact state that produced it."""
    runtime.start("T2", {"step": 0})
    for index, step in enumerate(("reconciled", "proposed", "committed"), start=1):
        runtime.checkpoint("T2", step, {"step": index})

    first = runtime.replay("T2", 1)
    assert first.state["step"] == 1
    last = runtime.replay("T2", 3)
    assert last.state["step"] == 3
    assert first.step != last.step


def test_an_interrupt_pauses_rather_than_returning(runtime):
    """The signature line is this interrupt. A runtime that returned normally
    here would let an unsigned plan continue to commit."""
    runtime.start("T3", {"step": 0})
    with pytest.raises(Interrupted):
        runtime.interrupt("T3", {"proposal": "draft"})


def test_resume_records_the_decision_and_returns_what_was_paused_on(runtime):
    """The contract is "here is the decision, give me back the thing I was
    deciding about" — the caller needs the proposal to carry on with, and the
    decision has to reach the audit trail rather than the return value."""
    runtime.start("T4", {"step": 0})
    try:
        runtime.interrupt("T4", {"proposal": "draft"})
    except Interrupted:
        pass

    assert runtime.resume("T4", "accepted") == {"proposal": "draft"}
    assert any(c.state.get("decision") == "accepted"
               for c in runtime.checkpoints["T4"]), "the decision must be checkpointed"


def test_resuming_a_thread_that_was_never_interrupted_raises(runtime):
    """Silently succeeding would let an unsigned plan through the signature
    line, which is the one thing that must never happen quietly."""
    runtime.start("T4b", {"step": 0})
    with pytest.raises(KeyError):
        runtime.resume("T4b", "accepted")


def test_threads_do_not_leak_into_each_other(runtime):
    """Two clinics on one deployment, or two encounters in one clinic."""
    runtime.start("A", {"who": "a"})
    runtime.start("B", {"who": "b"})
    runtime.checkpoint("A", "proposed", {"who": "a", "n": 1})
    runtime.checkpoint("B", "proposed", {"who": "b", "n": 1})
    assert runtime.replay("A", 1).state["who"] == "a"
    assert runtime.replay("B", 1).state["who"] == "b"


def test_replaying_a_step_that_does_not_exist_raises(runtime):
    """Silently returning the nearest checkpoint would make the audit trail
    lie about which state produced an output."""
    runtime.start("T5", {"step": 0})
    runtime.checkpoint("T5", "proposed", {"step": 1})
    with pytest.raises((IndexError, KeyError, ValueError)):
        runtime.replay("T5", 99)


def test_the_workflow_actually_exercises_the_contract(rules_pack):
    """None of the above matters if the encounter path does not use it."""
    from datetime import datetime

    from datagen.synthetic import make_patient
    from service.graph.workflow import run_encounter
    from service.router.router import default_router
    from service.signing import AuditLog, Signer

    seen: list[str] = []

    class Recording(InMemoryRuntime):
        def start(self, thread_id, state):
            seen.append("start")
            return super().start(thread_id, state)

        def checkpoint(self, thread_id, step, state):
            seen.append(f"checkpoint:{step}")
            return super().checkpoint(thread_id, step, state)

        def interrupt(self, thread_id, payload):
            seen.append("interrupt")
            return super().interrupt(thread_id, payload)

        def resume(self, thread_id, decision):
            seen.append("resume")
            return super().resume(thread_id, decision)

    site = rules_pack.sites["SITE-A"]
    run_encounter(
        make_patient(101, controlled=True), rules_pack, site, default_router(),
        Recording(), thread_id="W1",
        signer=Signer(site["practitioners"][0]["practitioner_id"], True),
        audit=AuditLog(), now=datetime(2026, 8, 29, 10, 0),
    )
    assert "start" in seen
    assert any(s.startswith("checkpoint:") for s in seen)
    assert "interrupt" in seen, "the signature line is a runtime interrupt"
    assert "resume" in seen


@pytest.fixture(scope="module")
def rules_pack():
    from service.packs.loader import load_pack

    return load_pack("id")
