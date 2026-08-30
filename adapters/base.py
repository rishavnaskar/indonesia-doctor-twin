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

    def fetch_between_visit_readings(self, patient_id: str) -> list:
        """Readings that arrived since the last encounter, with their sources.

        Home measurements, device uploads and dispensing events (SPEC §5.11).
        Each carries the provenance it arrived with — `patient_reported`,
        `device` or `derived` — and stamping that here rather than downstream is
        the whole reason this method exists on the port instead of being folded
        into `fetch_patient_state`. A home reading and a clinic reading are not
        interchangeable, and the between-visit loop decides differently for each.

        An adapter with no such channel returns an empty list. That is a
        different thing from a patient with no readings, and neither is a
        reason to invent one.
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
