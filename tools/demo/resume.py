"""What makes a run resumable: the thread id, and what is already stored.

A second `make` costs no model calls, and an edited guideline file costs them
all again. Both of those are properties of the id built here, which is a digest
of everything that could change the answer.
"""

from __future__ import annotations

import hashlib
import json

from tools.demo.store_access import forced_fresh, runtime
from tools.demo.wire import plain

# Bump when the shape of an encounter dict changes. It is part of the thread id,
# so a stored view built by older code is simply never found: the encounter
# re-runs rather than being handed to a renderer that no longer understands it.
#
# 2: the draft carries English patient instructions alongside the local-language
#    ones. Encounters stored under version 1 were drafted before that field
#    existed, so replaying them would render a page with no English on it and
#    look like the change had not shipped.
VIEW_VERSION = 2


def drafter_identity(router) -> str:
    """Who is drafting, named stably enough to key a cache on.

    Deliberately not `backend.version()`. That reports who *answered* — a
    hosted backend rewrites it to `model@served_by` after its first reply — so
    using it here would give the first encounter of a run a different key from
    the second, and no run would ever resume.

    The router's class is part of the key, because failing to name a backend is
    not itself a name. An earlier version returned "reference" whenever the
    lookup raised, which is how the reference reasoner reports itself — so a
    router that raises for a different reason, such as one that fails every
    draft, resumed the reference reasoner's successful results and reported
    zero failures. Two different drafters must never share a key.
    """
    kind = type(router).__name__
    try:
        backend = router.get(router.default).backend
    except (KeyError, AttributeError):
        return f"{kind}/reference"
    return f"{kind}/{getattr(backend, 'model', None) or backend.version()}"


def thread_id_for(scenario, rules, router) -> str:
    """A thread id derived from everything that could change the answer.

    Content-addressed on purpose. Re-running `make` re-uses what is already in
    the store, and the moment any input moves — a pack edited, a different site,
    a real model swapped in for the reference reasoner, a different patient —
    the id moves with it and the encounter runs again. The pack enters as its
    content digest rather than its declared version, because the version is
    written by hand and an edit that forgets to bump it would otherwise replay a
    stale answer. So the demo is fast on
    the second run without ever showing a result that belongs to a question
    nobody asked.

    This is also what makes `make live` usable: nine model calls for this page
    the first time, none the second, and an edit to a guideline file costs them
    again. `tools/live.py` does the same for the run's other five.
    """
    material = json.dumps(
        {
            "view": VIEW_VERSION,
            "scenario": scenario.key,
            "pack": f"{rules.pack_id}@{rules.version}+{rules.content_digest}",
            "site": scenario.site.get("site_id", ""),
            "drafter": drafter_identity(router),
            "tampered": bool(scenario.tamper),
            # The patient itself, because /clinic builds them in the browser and two
            # patients under one scenario key are two different encounters.
            "patient": plain(scenario.state),
        },
        sort_keys=True,
        default=str,
    )
    return f"DEMO-{scenario.key}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def stored(thread_id: str) -> dict | None:
    """A finished encounter from a previous run, if this is the same question."""
    if forced_fresh():
        return None
    history = runtime().checkpoints.get(thread_id) or []
    for entry in reversed(history):
        if entry.step == "rendered" and isinstance(entry.state, dict):
            return {**entry.state, "resumed": True}
    return None


class Tampered:
    """A router that corrupts the draft on its way out.

    Used to plant the errors the gate is supposed to catch. Holds no state of
    its own and never touches the router it wraps, so concurrent encounters
    cannot interfere with each other.
    """

    def __init__(self, router, tamper):
        self._router = router
        self._tamper = tamper

    def __getattr__(self, name):
        return getattr(self._router, name)

    def propose(self, state, rules, site=None, **kwargs):
        proposal = self._router.propose(state, rules, site, **kwargs)
        self._tamper(proposal)
        return proposal
