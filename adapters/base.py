"""The EMR adapter port.

Hospital systems are an integration detail. The moment the service layer knows
which one it is talking to, we have built a product for that vendor instead of
a clinical platform — and the fifty-first hospital, on a different system, then
needs a new product rather than a new adapter.

So: reads and the in-form panel go through this interface. The first concrete
adapter targets the open-source system that dominates the small-hospital
segment, which is why it was chosen — we have the source, so the safety net can
live inside the consultation form rather than on a second screen. That is a
sequencing advantage, not an architectural commitment.
"""

from __future__ import annotations

from typing import Protocol

from service.state.models import PatientState


class EMRAdapter(Protocol):
    """Everything the service layer is allowed to know about a hospital system."""

    name: str

    def fetch_patient_state(self, encounter_id: str) -> PatientState:
        """Map a native encounter into our canonical state.

        All provenance is stamped here. A value that arrives without a source
        is a bug in the adapter, not a default to be filled in downstream.
        """
        ...

    def render_panel(self, encounter_id: str, payload: dict) -> None:
        """Show the traffic light inside the consultation form.

        Green is silent. That silence is what keeps amber and red worth reading.
        """
        ...

    def queue_write(self, encounter_id: str, payload: dict) -> None:
        """Queue an outbound write.

        Every write is idempotent and replayable: roughly one site in five has
        unreliable connectivity and about one in twelve lacks 24-hour power, so
        a dropped connection mid-consultation must neither lose the encounter
        nor duplicate it on reconnect.
        """
        ...
