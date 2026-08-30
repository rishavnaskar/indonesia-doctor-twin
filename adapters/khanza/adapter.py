"""First concrete EMR adapter — a Phase 0 scaffold, not an implementation.

This file names a specific vendor, which is allowed here and forbidden under
/service. That asymmetry is the whole point of the adapter boundary: the
fifty-first hospital, on a different system, needs a new adapter rather than a
new product.

**Why this vendor first.** It dominates the small-hospital segment, it is open
source, it is recognised by the accreditation commission, and its repository
already contains a bridging package doing integrations of exactly this shape.
That last point is what matters: the pattern is not novel to that codebase, it
is how the codebase already works. The consequence is that assumption A1 — can
a traffic light render *inside* the consultation form — is answerable for most
of the estate, so the safety net can live in the form rather than on a second
screen. That is a sequencing advantage, not an architectural commitment.

**Every method raises, deliberately.** A stub returning an empty PatientState
would let the rest of the system run against silence and look healthy while
doing it, and "the patient has no medications" is a clinically dangerous thing
to invent. No schema is committed here either: a guessed schema in the
repository would look authoritative and would not be.

The work to make this real is BUILD.md Phase 0 — stand the application up from
its own migrations against a seeded database, write synthetic patients into the
native schema, and time the panel round trip. One engineer, two days.
"""

from __future__ import annotations

from service.state.models import PatientState


class KhanzaAdapter:
    name = "khanza"

    def __init__(self, dsn: str):
        self.dsn = dsn

    def fetch_patient_state(self, encounter_id: str) -> PatientState:
        raise NotImplementedError(
            "Phase 0 scaffold: no verified schema mapping yet. See docs/BUILD.md."
        )

    def render_panel(self, encounter_id: str, payload: dict) -> None:
        raise NotImplementedError("Phase 0: panel injection not implemented.")

    def fetch_between_visit_readings(self, patient_id: str) -> list:
        raise NotImplementedError(
            "Phase 0: no between-visit channel mapped yet. Dispensing data is "
            "the one source that exists without a patient-facing app."
        )

    def queue_write(self, encounter_id: str, payload: dict) -> None:
        raise NotImplementedError("Phase 0: outbound queue not implemented.")
