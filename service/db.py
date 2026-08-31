"""Postgres behind the same three interfaces the file backend implements.

Why a database at all, when append-only files already survive a power cut:

  * **Append-only becomes enforceable.** A JSONL audit log is append-only by
    convention — any text editor rewrites a signature and nothing records that
    it happened. The migration installs a trigger that raises on UPDATE and
    DELETE, so the constraint belongs to the database rather than to whoever
    remembered it.
  * **Concurrency.** Two clinicians at one site are two processes appending to
    one file, and interleaved writes are how a line ends up half from each.
  * **Questions the operator will actually ask.** "Which encounters are still
    unsent", "what did this practitioner sign last month" are one statement
    here and a full-file scan there.

Why it is optional, and why the file backend stays: about one facility in
twelve lacks 24-hour power and one in five has unreliable connectivity, so a
system that cannot start without a database is a system that cannot start.
`Store` prefers Postgres, falls back to files, and says which one it chose. The
conformance suite in tests/test_runtime_contract.py runs against both.

Nothing in this module knows anything clinical. It stores what it is given.
"""

from __future__ import annotations

import json
import os
from dataclasses import field, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).resolve().parents[1] / "db" / "migrations"

DEFAULT_DSN = "postgresql://clinician:clinician@localhost:5544/clinician"

# A refused connection must be fast. The default is to wait a long time on a
# host that is not listening, which turns "no database, use files" from a
# fallback into a hang.
CONNECT_TIMEOUT = 3


def dsn() -> str:
    return os.environ.get("CLINICIAN_DATABASE_URL", DEFAULT_DSN)


def connect(url: str | None = None):
    """A live connection, or None if there is not one.

    Returns rather than raises. The caller's job is to carry on with files, not
    to handle an exception for a condition that is expected in this deployment.
    """
    try:
        import psycopg
    except ModuleNotFoundError:
        return None
    try:
        return psycopg.connect(url or dsn(), autocommit=True,
                               connect_timeout=CONNECT_TIMEOUT)
    except Exception:  # noqa: BLE001 - every failure means the same thing here
        return None


def available(url: str | None = None) -> bool:
    conn = connect(url)
    if conn is None:
        return False
    conn.close()
    return True


def migrate(conn) -> list[str]:
    """Apply pending migrations in filename order. Returns what it applied.

    Postgres runs the same directory itself on a fresh container, so on that
    path every file is already applied before this runs — but the tracking
    table is not populated, and re-running is how it finds out. Both paths
    converge because every statement in a migration is safe to run twice.
    """
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name TEXT PRIMARY KEY,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}

    fresh = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)"
                        " ON CONFLICT DO NOTHING", (path.name,))
        fresh.append(path.name)
    return fresh


TABLES = ("checkpoints", "signatures", "outbound")


def reset(conn) -> dict[str, int]:
    """Empty every table, and say how much was destroyed.

    The append-only triggers refuse DELETE, which is the point of them — so
    this disables them for the length of the statement and puts them back. That
    is deliberately the only place in the codebase that does, and it is a
    separate command a person has to type rather than anything a run can reach.

    The honest framing: this is not "clearing a cache". It is destroying a
    clinical audit trail, which in a real deployment would be unlawful. It
    exists because a prototype's store fills with synthetic demo runs and
    starting a recording from a clean slate is a real need. `/clinic`'s own
    *Clear this list* does not do this: it writes a marker forward and deletes
    nothing, which is what the product does. This is the operator's hammer.

    `/clinic` also carries a *Delete everything* button that does reach this,
    which weakens the "a person has to type it" protection this used to rely on.
    So the protection moved rather than went: the route refuses without an
    explicit confirmation, and `reset_allowed()` switches it off by default
    wherever the deployment is public, because a wipe button on a link anyone
    can open is one misclick from emptying the store under whoever is reading.
    """
    counts = {}
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
            # TRUNCATE would not fire row triggers, but DISABLE/ENABLE is
            # explicit about what is being suspended and why. A reader should
            # not have to know which statements bypass which triggers to see
            # that a guarantee is being lifted here.
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            cur.execute(f"TRUNCATE {table} RESTART IDENTITY")
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
    return counts


# --------------------------------------------------------------- serialisation


def _encode(obj: Any) -> Any:
    """How a workflow state becomes a JSON document.

    Dataclasses go in field by field rather than as their repr. That is the
    difference between an audit trail a person can read and one a program can
    replay, and replay is the answer to "why did the system say that".
    """
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    return str(obj)


def as_json(obj: Any) -> str:
    return json.dumps(obj, default=_encode)


def _jsonb(obj: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(obj, dumps=as_json)


# -------------------------------------------------------------------- backends

from service.emit.queue import ItemStatus, OutboundQueue, QueueItem  # noqa: E402
from service.graph.runtime import Checkpoint, InMemoryRuntime  # noqa: E402
from service.signing import AuditLog, SignatureRecord  # noqa: E402


@dataclass
class PostgresRuntime(InMemoryRuntime):
    """The reference semantics, with the checkpoints in a table.

    Reads take the newest row per (thread_id, sequence) — `DISTINCT ON`, ordered
    by the serial id — which reproduces the file backend's "later entries win"
    without ever overwriting the earlier attempt. A thread that crashed and was
    re-run keeps both, and the trail shows that it happened.
    """

    conn: Any = None

    def __post_init__(self) -> None:
        if self.conn is not None:
            self._load()

    def start(self, thread_id: str, state: Any) -> None:
        # Never clears history, for the same reason the file backend does not:
        # a restarted encounter must not erase what the system saw before it
        # fell over.
        self.checkpoints.setdefault(thread_id, [])
        self.checkpoint(thread_id, "start", state)

    def checkpoint(self, thread_id: str, step: str, state: Any) -> Checkpoint:
        entry = super().checkpoint(thread_id, step, state)
        if self.conn is not None:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO checkpoints (thread_id, sequence, step, state)"
                    " VALUES (%s, %s, %s, %s)",
                    (entry.thread_id, entry.sequence, entry.step, _jsonb(entry.state)),
                )
        return entry

    def threads(self) -> list[str]:
        return sorted(self.checkpoints)

    def _load(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (thread_id, sequence) thread_id, sequence, step, state"
                " FROM checkpoints ORDER BY thread_id, sequence, id DESC"
            )
            for thread_id, sequence, step, state in cur.fetchall():
                history = self.checkpoints.setdefault(thread_id, [])
                entry = Checkpoint(thread_id, step, state, sequence)
                if sequence < len(history):
                    history[sequence] = entry
                else:
                    history.append(entry)


@dataclass
class PostgresAuditLog(AuditLog):
    """Signatures, in a table that refuses to let them be edited."""

    conn: Any = None

    def __post_init__(self) -> None:
        if self.conn is not None:
            self._load()

    def _write(self, record: SignatureRecord) -> None:
        if self.conn is None:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO signatures (practitioner_id, role, licence_expires,"
                " decision, proposal_provenance, signed_at, rejection_reason, edit_diff)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (record.practitioner_id, record.role, record.licence_expires,
                 record.decision, _jsonb(list(record.proposal_provenance)),
                 record.signed_at, record.rejection_reason, record.edit_diff),
            )

    def _load(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT practitioner_id, role, licence_expires, decision,"
                " proposal_provenance, signed_at, rejection_reason, edit_diff"
                " FROM signatures ORDER BY id"
            )
            for row in cur.fetchall():
                self.records.append(SignatureRecord(
                    practitioner_id=row[0], role=row[1], licence_expires=row[2],
                    decision=row[3], proposal_provenance=tuple(row[4]),
                    signed_at=row[5], rejection_reason=row[6], edit_diff=row[7],
                ))


@dataclass
class PostgresQueue(OutboundQueue):
    """The outbound queue as a log of state transitions.

    Enqueue writes 'pending'; a drain writes the outcome. The current state of
    an item is its newest row, so the attempt history stays intact — which is
    the thing an operator at a site with one bar of signal actually wants to
    see.
    """

    conn: Any = None

    def __post_init__(self) -> None:
        if self.conn is not None:
            self._load()

    def _append(self, item: QueueItem) -> None:
        if self.conn is None:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO outbound (idempotency_key, kind, payload, status,"
                " attempts, last_error, enqueued_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (item.idempotency_key, item.kind, _jsonb(item.payload),
                 item.status.value, item.attempts, item.last_error, item.enqueued_at),
            )

    def _load(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (idempotency_key) idempotency_key, kind, payload,"
                " status, attempts, last_error, enqueued_at,"
                # DISTINCT ON keeps the newest row per key, so its id is the
                # last transition. Queue position is where the item *entered*,
                # which is the first — window functions are evaluated before
                # DISTINCT, so this survives the deduplication above it.
                " min(id) OVER (PARTITION BY idempotency_key) AS entered"
                " FROM outbound ORDER BY idempotency_key, id DESC"
            )
            rows = cur.fetchall()
        # Ordered by arrival, not by key, because a queue is a queue.
        for row in sorted(rows, key=lambda r: r[7]):
            item = QueueItem(
                idempotency_key=row[0], kind=row[1], payload=row[2],
                status=ItemStatus(row[3]), attempts=row[4], last_error=row[5],
                enqueued_at=row[6],
            )
            if item.idempotency_key not in self.items:
                self._order.append(item.idempotency_key)
            self.items[item.idempotency_key] = item
