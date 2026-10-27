"""The one store this process talks to, and the one way to destroy it.

Split out of run.py because the lifetime rules here are subtle and were worth
stating in one place: the store is opened once per process, the runtime is
shared between concurrent encounters, and resetting has to drop both caches or
the process keeps serving encounters that no longer exist anywhere.
"""

from __future__ import annotations

import os
import threading

_STORE = None
_RUNTIME = None
_STORE_LOCK = threading.Lock()


def forced_fresh() -> bool:
    """CLINICIAN_FRESH=1 re-runs work even when a stored result matches.

    Re-exported rather than re-implemented: the surface and the live runner
    must agree about what the flag means, and a convention implemented twice
    is a convention that drifts.
    """
    from service.store import forced_fresh as _forced_fresh

    return _forced_fresh()


def store():
    """The deployment's durable store — Postgres if one is reachable, else files.

    Opened once per process and shared, because the connection is the expensive
    part. The objects built *from* it are per-encounter: three encounters run
    concurrently, and a queue shared between threads has a read-then-write in
    `enqueue` that nothing here would notice going wrong. Rebuilding costs a
    reload of a table that a demo keeps small.
    """
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            from service.store import Store

            _STORE = Store()
    return _STORE


def runtime():
    """The durable runtime, loaded once per process.

    Unlike the queue and the audit log this one is shared between the three
    concurrent encounters, because it is also the thing they look themselves up
    in — rebuilding it per encounter would re-read every checkpoint the
    deployment has ever written, once per patient. Sharing is safe here in a way
    it is not for the queue: distinct thread ids mean distinct lists, and
    `setdefault` on the thread dict is atomic.
    """
    global _RUNTIME
    # store() outside the lock, not inside it: threading.Lock is not reentrant,
    # and taking it here and again in store() deadlocks the first caller.
    durable = store()
    with _STORE_LOCK:
        if _RUNTIME is None:
            _RUNTIME = durable.runtime()
    return _RUNTIME



def reset_allowed() -> bool:
    """Whether the surface is permitted to destroy the store.

    Off on a hosted deployment unless explicitly switched on, because the public
    demo is a link anyone can open and a wipe button on it is one misclick away
    from emptying the store under whoever is reading at the time. Locally it is
    on, since that is the machine whose data it is.

    Set CLINICIAN_ALLOW_RESET=1 to enable it anywhere, or =0 to refuse it
    everywhere including locally.
    """
    explicit = os.environ.get("CLINICIAN_ALLOW_RESET")
    if explicit is not None:
        return explicit == "1"
    return os.environ.get("CLINICIAN_HOSTED", "") != "1"


def reset_everything() -> dict:
    """Destroy the store and drop every cache built from it.

    Resetting the store alone would leave this process serving encounters that
    no longer exist anywhere, which looks like the reset silently failed. The
    runtime is cached per process and the scripted page is cached in the build,
    so both have to go with it.
    """
    global _RUNTIME, _STORE

    counts = store().reset()
    with _STORE_LOCK:
        # Both are process-cached and both are built from what was just
        # destroyed. A runtime holding a connection to an emptied database is
        # fine; one holding checkpoints that no longer exist is not.
        _RUNTIME = None
        _STORE = None
    return counts


