"""What the database backend adds over the file backend.

The shared semantics are tested once, in test_runtime_contract.py, against all
three implementations. What is here is only what is true of Postgres and not of
a file: the constraints the database enforces on its own, and the fallback that
lets the system run without it.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from service.emit.queue import ItemStatus
from service.signing import SignatureRecord
from tests.pgfixture import connection, drop


@pytest.fixture
def conn():
    connected = connection()
    if connected is None:
        pytest.skip("no database reachable — `docker compose up -d` to run this")
    yield connected
    drop(connected)


def _signature(**overrides) -> SignatureRecord:
    fields = dict(
        practitioner_id="DR-1", role="doctor", licence_expires=date(2027, 1, 1),
        decision="accepted", proposal_provenance=("m@s", "p@1", "c@1"),
        signed_at=datetime(2026, 8, 30, 10, 0), rejection_reason=None, edit_diff=None,
    )
    fields.update(overrides)
    return SignatureRecord(**fields)


# ------------------------------------------------------- constraints, enforced


@pytest.mark.parametrize("table", ["signatures", "checkpoints", "outbound"])
@pytest.mark.parametrize("statement", ["UPDATE {} SET id = id", "DELETE FROM {}"])
def test_the_database_refuses_to_let_history_be_rewritten(conn, table, statement):
    """The reason this is worth a database rather than a file.

    A JSONL audit log is append-only by convention: any text editor rewrites a
    signature and nothing records that it happened. Here the constraint is the
    database's, so it holds against the application, against a migration script
    and against somebody at a psql prompt.

    It raises rather than silently discarding the write. An ignored UPDATE looks
    to the caller exactly like a successful one, which is the worst available
    outcome for a table whose whole job is being trustworthy.
    """
    from service.db import PostgresAuditLog, PostgresQueue, PostgresRuntime

    PostgresRuntime(conn=conn).start("T", {"a": 1})
    PostgresAuditLog(conn=conn).append(_signature())
    PostgresQueue(conn=conn).enqueue("bundle", {"a": 1}, "K1", datetime(2026, 8, 30, 10, 0))

    with pytest.raises(Exception, match="append-only"):
        with conn.cursor() as cur:
            cur.execute(statement.format(table))


def test_a_decision_outside_the_three_the_system_knows_is_refused(conn):
    """The enum is in the application, but this table outlives the process that
    wrote it. A later migration script or a psql session will not import it."""
    with pytest.raises(Exception, match="constraint|check"):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO signatures (practitioner_id, role, licence_expires,"
                " decision, proposal_provenance, signed_at)"
                " VALUES ('DR-1', 'doctor', '2027-01-01', 'auto_approved', '[]', now())"
            )


# -------------------------------------------------------------- what persists


def test_signatures_survive_a_new_connection(conn):
    from service.db import PostgresAuditLog, connect

    PostgresAuditLog(conn=conn).append(_signature())
    PostgresAuditLog(conn=conn).append(_signature(practitioner_id="DR-2", decision="rejected",
                                                  rejection_reason="disagreed"))

    reopened = connect()
    with reopened.cursor() as cur:
        cur.execute(f'SET search_path TO "{conn._test_schema}"')
    records = PostgresAuditLog(conn=reopened).records
    reopened.close()

    assert [r.practitioner_id for r in records] == ["DR-1", "DR-2"]
    assert records[1].rejection_reason == "disagreed"
    assert records[0].proposal_provenance == ("m@s", "p@1", "c@1")


def test_the_queue_keeps_every_attempt_not_just_the_outcome(conn):
    """An operator at a site with one bar of signal asks how many times a bundle
    failed and with what error. A queue that overwrites its own rows cannot say.
    """
    from service.db import PostgresQueue

    queue = PostgresQueue(conn=conn)
    queue.enqueue("bundle", {"a": 1}, "K1", datetime(2026, 8, 30, 10, 0))
    queue.mark("K1", ItemStatus.PENDING, "TimeoutError: no route to host")
    queue.mark("K1", ItemStatus.SENT)

    with conn.cursor() as cur:
        cur.execute("SELECT status, last_error FROM outbound"
                    " WHERE idempotency_key = 'K1' ORDER BY id")
        history = cur.fetchall()

    assert [row[0] for row in history] == ["pending", "pending", "sent"]
    assert "TimeoutError" in history[1][1]
    # ... and the current state is still just the item.
    assert PostgresQueue(conn=conn).items["K1"].status is ItemStatus.SENT


def test_queue_order_is_arrival_order_not_last_transition(conn):
    """A queue is a queue. Deduplicating to the newest row per key makes the
    obvious ordering the *last* thing that happened to an item, which would put
    a retried bundle behind one enqueued after it."""
    from service.db import PostgresQueue

    queue = PostgresQueue(conn=conn)
    for n in range(1, 4):
        queue.enqueue("bundle", {"n": n}, f"K{n}", datetime(2026, 8, 30, 10, n))
    queue.mark("K1", ItemStatus.PENDING, "retry")  # newest row is now K1's

    assert [i.idempotency_key for i in PostgresQueue(conn=conn)] == ["K1", "K2", "K3"]


def test_a_rerun_of_a_thread_does_not_erase_the_attempt_that_crashed(conn):
    """Same semantics as the file backend, arrived at differently: the file
    overwrites the position on load, the table keeps both rows and reads the
    newest. The earlier attempt stays on the record either way."""
    from service.db import PostgresRuntime

    PostgresRuntime(conn=conn).start("T9", {"attempt": 1})
    second = PostgresRuntime(conn=conn)
    second.checkpoints.pop("T9", None)  # a fresh process, mid-crash-recovery
    second.start("T9", {"attempt": 2})

    with conn.cursor() as cur:
        cur.execute("SELECT state FROM checkpoints WHERE thread_id = 'T9' ORDER BY id")
        assert [row[0]["attempt"] for row in cur.fetchall()] == [1, 2]
    assert PostgresRuntime(conn=conn).replay("T9", 0).state["attempt"] == 2


def test_a_patient_state_is_stored_field_by_field_not_as_its_repr(conn):
    """Replay is the answer to "why did the system say that", and a runtime that
    persists `PatientState(patient_id='P-1', ...)` as a string can be read but
    not replayed."""
    from datagen.synthetic import make_patient
    from service.db import PostgresRuntime

    PostgresRuntime(conn=conn).start("T10", make_patient(101, controlled=True))

    state = PostgresRuntime(conn=conn).replay("T10", 0).state
    assert isinstance(state, dict), "a dataclass must not be persisted as its repr"
    assert state["patient_id"]
    assert isinstance(state["observations"], list)


# ---------------------------------------------------------------- the fallback


def test_migrations_are_idempotent(conn):
    """Postgres runs the same directory itself on a fresh container, so the
    application's first startup always re-applies files that are already there.
    """
    from service.db import migrate

    assert migrate(conn) == [], "already applied by the fixture"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM schema_migrations")
    assert migrate(conn), "re-running against an existing schema must not raise"


def test_the_store_falls_back_to_files_when_nothing_is_listening(tmp_path, monkeypatch):
    """A clinical system that will not start without a database is a clinical
    system that does not start. One site in twelve lacks 24-hour power."""
    from service.store import Store

    monkeypatch.setenv("CLINICIAN_DATABASE_URL", "postgresql://x@127.0.0.1:1/none")
    store = Store(tmp_path / "s")

    assert store.backend == "files"
    assert store.summary()["backend"] == "files"
    store.audit_log().append(_signature())
    assert store.checkpoints.parent.exists()


def test_the_store_says_which_backend_it_chose(conn, monkeypatch):
    """Silently degrading to files would make "did that signature persist" a
    question nobody thought to ask."""
    from service.store import Store

    monkeypatch.delenv("CLINICIAN_STORE_BACKEND", raising=False)
    store = Store(connection=conn)
    assert store.backend == "postgres"
    assert store.summary()["backend"] == "postgres"


def test_the_location_never_carries_the_password(monkeypatch):
    """summary() is printed by the demo surface and by `tools.store`."""
    from service.store import Store

    monkeypatch.setenv("CLINICIAN_DATABASE_URL",
                       "postgresql://someone:hunter2@db.example:5544/clinician")
    store = Store(connection=object())
    assert "hunter2" not in store._location()
    assert "db.example:5544/clinician" == store._location()


# --------------------------------------------------------------------- reset


def test_reset_empties_every_table_and_reports_what_it_destroyed(conn):
    from service.db import PostgresAuditLog, PostgresQueue, PostgresRuntime, reset

    PostgresRuntime(conn=conn).start("T", {"a": 1})
    PostgresAuditLog(conn=conn).append(_signature())
    PostgresQueue(conn=conn).enqueue("bundle", {"a": 1}, "K1", datetime(2026, 8, 30, 10, 0))

    destroyed = reset(conn)

    assert destroyed == {"checkpoints": 1, "signatures": 1, "outbound": 1}
    assert PostgresRuntime(conn=conn).threads() == []
    assert PostgresAuditLog(conn=conn).records == []
    assert len(PostgresQueue(conn=conn)) == 0


@pytest.mark.parametrize("table", ["signatures", "checkpoints", "outbound"])
def test_reset_puts_the_append_only_triggers_back(conn, table):
    """`reset` is the only code that suspends them, and a reset that left them
    off would turn the store's central guarantee into something that held until
    the first time somebody started afresh — silently, because an append-only
    table behaves identically to a mutable one right up until someone mutates it.
    """
    from service.db import PostgresAuditLog, PostgresQueue, PostgresRuntime, reset

    reset(conn)

    # Rows first. A row-level trigger on an empty table fires zero times, so an
    # UPDATE against one succeeds whether the trigger is there or not — which is
    # exactly how a missing trigger would hide.
    PostgresRuntime(conn=conn).start("T", {"a": 1})
    PostgresAuditLog(conn=conn).append(_signature())
    PostgresQueue(conn=conn).enqueue("bundle", {"a": 1}, "K1", datetime(2026, 8, 30, 10, 0))

    with pytest.raises(Exception, match="append-only"):
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET id = id")


def test_the_file_store_resets_too(tmp_path, monkeypatch):
    """A developer on files should not have to learn a different command."""
    from service.store import Store

    monkeypatch.setenv("CLINICIAN_DATABASE_URL", "postgresql://x@127.0.0.1:1/none")
    store = Store(tmp_path / "s")
    store.audit_log().append(_signature())
    assert store.summary()["signatures"] == 1

    destroyed = store.reset()

    assert destroyed["backend"] == "files"
    assert destroyed["signatures"] == 1
    assert store.summary()["signatures"] == 0
    assert not store.audit.exists()
