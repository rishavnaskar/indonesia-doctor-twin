"""Interrupt/resume/replay semantics — the signature line and the audit story."""

import pytest

from service.graph.runtime import Interrupted, InMemoryRuntime


def test_interrupt_pauses_before_the_irreversible_step():
    runtime = InMemoryRuntime()
    runtime.start("t1", {"step": "propose"})
    with pytest.raises(Interrupted) as excinfo:
        runtime.interrupt("t1", {"proposal": "draft"})
    assert excinfo.value.thread_id == "t1"


def test_resume_carries_the_human_decision():
    runtime = InMemoryRuntime()
    runtime.start("t1", {})
    with pytest.raises(Interrupted):
        runtime.interrupt("t1", {"proposal": "draft"})
    payload = runtime.resume("t1", "accepted")
    assert payload == {"proposal": "draft"}


def test_replay_reconstructs_what_the_system_saw_not_what_it_became():
    runtime = InMemoryRuntime()
    state = {"bp": 150}
    runtime.start("t1", state)
    state["bp"] = 120  # the live object moves on
    assert runtime.replay("t1", 0).state == {"bp": 150}


def test_resuming_without_an_interrupt_is_an_error():
    runtime = InMemoryRuntime()
    runtime.start("t1", {})
    with pytest.raises(KeyError):
        runtime.resume("t1", "accepted")
