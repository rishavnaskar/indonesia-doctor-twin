"""A throwaway Postgres schema, or a skip.

Every Postgres test runs inside a schema created for it and dropped afterwards.
Two reasons, and the second is the important one:

  * tests share thread ids (T1, T2 ...) and the store is append-only, so a
    second run against the same tables would replay onto the first
  * a developer's database is a real store. A suite that truncates tables to
    isolate itself is one `CLINICIAN_DATABASE_URL` away from deleting the
    signatures it was written to protect.

Skips rather than fails when nothing is listening. The database is optional by
design, and a suite that cannot run without a container would contradict that.
"""

from __future__ import annotations

import os
import uuid

import pytest


def connection():
    """A connection with a private schema, or None."""
    from service import db

    conn = db.connect()
    if conn is None:
        return None
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    db.migrate(conn)
    conn._test_schema = schema  # noqa: SLF001 - teardown needs it back
    return conn


def drop(conn) -> None:
    schema = getattr(conn, "_test_schema", None)
    if schema:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO public")
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


requires_postgres = pytest.mark.skipif(
    not os.environ.get("CLINICIAN_DATABASE_URL", "1"),
    reason="no database configured",
)
