"""First concrete EMR adapter — not yet implemented against the real system.

This file names a specific vendor, which is allowed here and forbidden under
/service. That asymmetry is the whole point of the adapter boundary.

Every method raises. A stub that returned an empty PatientState would let the
rest of the system run against silence and look healthy while doing so, and
"the patient has no medications" is a clinically dangerous thing to invent.
"""

from __future__ import annotations

from service.state.models import PatientState


class KhanzaAdapter:
    name = "khanza"

    def __init__(self, dsn: str):
        self.dsn = dsn

    def fetch_patient_state(self, encounter_id: str) -> PatientState:
        raise NotImplementedError(
            "Phase 0: no verified schema mapping yet. See adapters/khanza/README.md."
        )

    def render_panel(self, encounter_id: str, payload: dict) -> None:
        raise NotImplementedError("Phase 0: panel injection not implemented.")

    def queue_write(self, encounter_id: str, payload: dict) -> None:
        raise NotImplementedError("Phase 0: outbound queue not implemented.")
