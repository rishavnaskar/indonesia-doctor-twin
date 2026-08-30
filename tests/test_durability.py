"""What survives the process ending.

BUILD.md says a checkpoint is a recovery point for interruption, timeout,
human handoff and *service restart*, and that replay is how a regulator is
answered when they ask why the system said something. Neither was true while
checkpoints and the signature log lived in dictionaries — and about one facility
in twelve lacks 24-hour power, so "the process died" is the ordinary case.

These tests are the difference between claiming durability and having it.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from service.graph.runtime import Checkpoint, FileRuntime
from service.signing import AuditLog, SignatureRecord
from service.store import Store


def test_checkpoints_outlive_the_process(tmp_path):
    path = tmp_path / "cp.jsonl"
    runtime = FileRuntime(path=path)
    runtime.start("ENC-1", {"step": 0})
    runtime.checkpoint("ENC-1", "proposed", {"step": 1, "sbp": 160})

    reopened = FileRuntime(path=path)
    assert reopened.threads() == ["ENC-1"]
    assert reopened.replay("ENC-1", 1).state == {"step": 1, "sbp": 160}


def test_a_restart_does_not_erase_what_came_before(tmp_path):
    """`start` clears history on the in-memory runtime. A restarted encounter
    must not erase what the system saw before it fell over."""
    path = tmp_path / "cp.jsonl"
    first = FileRuntime(path=path)
    first.start("ENC-2", {"step": 0})
    first.checkpoint("ENC-2", "proposed", {"step": 1})

    second = FileRuntime(path=path)
    second.start("ENC-2", {"step": 0})
    assert len(second.checkpoints["ENC-2"]) >= 2


def test_a_truncated_checkpoint_line_is_survivable(tmp_path):
    """A power cut mid-write leaves a partial line. Refusing to open the file
    would lose every checkpoint behind it."""
    path = tmp_path / "cp.jsonl"
    runtime = FileRuntime(path=path)
    runtime.start("ENC-3", {"step": 0})
    runtime.checkpoint("ENC-3", "proposed", {"step": 1})
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"thread_id": "ENC-4", "step": "pro')

    reopened = FileRuntime(path=path)
    assert reopened.threads() == ["ENC-3"]
    assert len(reopened.damaged) == 1, "the loss must be visible, not silent"


def test_a_signature_outlives_the_process(tmp_path):
    """The signature is what makes an output lawful. A record of it that
    disappears on restart is not a record."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=path)
    log.append(SignatureRecord(
        practitioner_id="PRAC-A-001", role="internist",
        licence_expires=date(2027, 3, 31), decision="accepted",
        proposal_provenance=("m@1", "p@1", "c@1"),
        signed_at=datetime(2026, 8, 29, 10, 30)))

    reopened = AuditLog(path=path)
    assert len(reopened.records) == 1
    record = reopened.records[0]
    assert record.practitioner_id == "PRAC-A-001"
    assert record.licence_expires == date(2027, 3, 31)
    # The pin is the point: it says which model, prompt and rule set produced
    # the draft this person put their licence behind.
    assert record.proposal_provenance == ("m@1", "p@1", "c@1")


def test_a_damaged_signature_line_does_not_lose_the_rest(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=path)
    log.append(SignatureRecord("PRAC-A-001", "internist", date(2027, 3, 31),
                               "accepted", ("m@1", "p@1", "c@1"),
                               datetime(2026, 8, 29, 10, 30)))
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"practitioner_id": "PRA')

    reopened = AuditLog(path=path)
    assert len(reopened.records) == 1
    assert len(reopened.damaged) == 1


def test_an_in_memory_log_still_works_without_a_path(tmp_path):
    """Persistence is opt-in; the tests and the scorecard must not need a disk."""
    log = AuditLog()
    log.append(SignatureRecord("P", "r", date(2027, 1, 1), "accepted",
                               ("m@1", "p@1", "c@1"), datetime(2026, 8, 29, 10, 0)))
    assert len(log.records) == 1


def test_the_store_reports_what_it_holds(tmp_path):
    store = Store(tmp_path / "s")
    runtime, log = store.runtime(), store.audit_log()
    runtime.start("ENC-9", {"step": 0})
    log.append(SignatureRecord("P", "r", date(2027, 1, 1), "accepted",
                               ("m@1", "p@1", "c@1"), datetime(2026, 8, 29, 10, 0)))
    store.outbound().enqueue("encounter_bundle", {"n": 1}, "k1",
                             datetime(2026, 8, 29, 10, 0))

    facts = Store(tmp_path / "s").summary()
    assert facts["encounters_checkpointed"] == 1
    assert facts["signatures"] == 1
    assert facts["queued"] == 1
    assert facts["damaged_lines"] == 0


def test_two_encounters_never_share_a_trail(tmp_path):
    """A thread id built from a position in a run collided between runs, so two
    different encounters appended to one audit trail. In memory it was
    invisible; on disk it is a corrupted record."""
    path = tmp_path / "cp.jsonl"
    runtime = FileRuntime(path=path)
    runtime.start("SYN-1-run-a-0", {"who": "first"})
    runtime.start("SYN-1-run-b-0", {"who": "second"})

    reopened = FileRuntime(path=path)
    assert len(reopened.threads()) == 2
    assert reopened.replay("SYN-1-run-a-0", 0).state["who"] == "first"
    assert reopened.replay("SYN-1-run-b-0", 0).state["who"] == "second"


def test_the_durable_runtime_satisfies_the_same_contract(tmp_path):
    """It is the contract suite that makes this swappable rather than a
    reimplementation with its own opinions."""
    runtime = FileRuntime(path=tmp_path / "cp.jsonl")
    runtime.start("T", {"step": 0})
    entry = runtime.checkpoint("T", "proposed", {"step": 1})
    assert isinstance(entry, Checkpoint)

    from service.graph.runtime import Interrupted

    with pytest.raises(Interrupted):
        runtime.interrupt("T", {"proposal": "draft"})
    assert runtime.resume("T", "accepted") == {"proposal": "draft"}
