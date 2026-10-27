"""The interactive surface: build a patient, then run the clinician.

Kept apart from render.py because it is a different thing. That page is a
record of a run; this one is a place to poke the system and watch it react.
Both drive the identical pipeline: a demo whose interactive mode took a
different path through the system would be demonstrating something other
than the system.

The page itself is templates/clinic.html. It takes no substitutions, because
everything on it is fetched from the API after load rather than baked in,
which is what lets a patient built in the browser be re-run without a reload.
"""

from __future__ import annotations

from tools.demo.templates import load

TEMPLATE = "clinic.html"


def clinic_page() -> str:
    """The /clinic page, ready to serve."""
    return load(TEMPLATE)
