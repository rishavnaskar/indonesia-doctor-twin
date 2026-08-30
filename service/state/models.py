"""Longitudinal patient state.

The durable asset. Everything else in this system is replaceable — models get
swapped, prompts get rewritten, the orchestration library could change. This
does not.

Three design rules from SPEC-V1 §3, enforced here rather than by convention:

  1. Every clinical field carries provenance. `source` is mandatory on
     observations and medications, and a model may never treat a
     patient-reported value as equivalent to a lab-confirmed one.
  2. State is versioned. We must be able to reconstruct exactly what the system
     saw at the moment it produced an output. Not retrofittable.
  3. The interoperability format is a boundary, not the canonical model. Nothing
     in here is shaped by an exchange profile.

Note on naming: no EMR product, country, payer, drug or guideline is named in
this module, or anywhere under /service. `Source.EMR` is deliberately generic —
the moment /service knows which hospital system it is talking to, we have built
an integration instead of a platform. Adapters do the mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Source(str, Enum):
    """Where a value came from. Never inferred, never defaulted."""

    EMR = "emr"
    PATIENT_REPORTED = "patient_reported"
    DEVICE = "device"
    DERIVED = "derived"
    CLINICIAN_ENTERED = "clinician_entered"


@dataclass(frozen=True)
class Observation:
    code: str  # sbp, dbp, k, egfr, creatinine, hba1c, ...
    value: float
    unit: str
    taken_at: date
    source: Source
    method: str | None = None


@dataclass(frozen=True)
class Medication:
    molecule: str
    mg_per_dose: float
    doses_per_day: int
    source: Source
    since: date | None = None
    adherence_signal: str | None = None  # good | gaps | unknown

    @property
    def mg_daily(self) -> float:
        return self.mg_per_dose * self.doses_per_day


@dataclass(frozen=True)
class Diagnosis:
    code: str
    onset: date | None = None
    status: str = "active"
    system: str = "ICD-10"


@dataclass(frozen=True)
class Allergy:
    substance: str  # molecule or drug class
    reaction: str | None = None


@dataclass(frozen=True)
class Intolerance:
    """Powers the ARB restriction.

    `documented_at` is the date the intolerance was recorded. The restriction
    reads "documented ACE-inhibitor intolerance of at least one month", which is
    genuinely ambiguous between (a) the record has stood for a month and (b) the
    patient took the drug for a month before stopping. We implement (a) and
    surface it as SPEC-V1 §10 Q4 for the clinical lead. Switching readings is a
    one-line change here plus a pack value.
    """

    molecule: str
    drug_class: str
    documented_at: date
    reaction: str | None = None


@dataclass(frozen=True)
class PriorEncounter:
    encounter_id: str
    encounter_date: date
    sbp: float | None = None
    dbp: float | None = None
    decision: str | None = None
    signed_by: str | None = None


@dataclass
class PatientState:
    """A person with a history, not a diagnosis task."""

    patient_id: str
    age: int
    sex: str
    as_of: date

    diagnoses: list[Diagnosis] = field(default_factory=list)
    medications: list[Medication] = field(default_factory=list)
    allergies: list[Allergy] = field(default_factory=list)
    intolerances: list[Intolerance] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    encounters: list[PriorEncounter] = field(default_factory=list)

    # Derived or situational booleans: has_dm, has_ckd, has_lv_dysfunction,
    # pregnancy_positive, is_first_presentation, on_dialysis, ...
    flags: dict[str, bool] = field(default_factory=dict)

    # From the bounded intake interview only. Never free text.
    symptoms: dict[str, bool] = field(default_factory=dict)

    # Untrusted text: whatever the patient typed, plus free-text carried over
    # from the record. It exists because reconciliation needs it, and it is
    # quarantined here on purpose.
    #
    # No gate check reads this field, and none ever should. That is the
    # structural answer to prompt injection (SPEC-V1 F11): text the system did
    # not author can influence what the model *proposes*, but it cannot reach
    # the rules that decide whether the proposal renders. There is a test that
    # asserts a proposal's fate is identical with and without hostile text here.
    intake_notes: str = ""

    version: int = 1

    # Whether this record is generated rather than a real person's.
    #
    # Load-bearing, not documentation. Health data must be processed
    # in-country, and a hosted model endpoint is outside that boundary. The
    # hosted backend refuses to send anything whose provenance is not synthetic,
    # so pointing this prototype at a real record fails closed instead of
    # quietly exporting a patient. Defaults to False: real until proven
    # otherwise is the safe direction for this particular flag.
    is_synthetic: bool = False

    # ---------------------------------------------------------------- lookups

    def latest(self, code: str) -> Observation | None:
        """Most recent reading of `code`.

        Ties on date resolve to the most recently *recorded* value, because
        repeat same-day readings are routine here — the measurement standard
        asks for a mean of at least two, and a nurse re-checking a high
        pressure after five minutes' rest produces exactly this shape. An
        earlier version used max(), which resolves ties by list position and so
        could return the first reading of the day rather than the confirmatory
        one. That is the wrong reading to act on.
        """
        best: Observation | None = None
        for obs in self.observations:
            if obs.code != code:
                continue
            # A reading dated after this encounter was not available at this
            # encounter. `as_of` is what the system saw at this moment, so a
            # future-dated observation is excluded rather than used.
            #
            # This is a safety property, not tidiness. Age is measured as
            # as_of - taken_at, so a future date produces a negative age and
            # satisfies *every* freshness rule in the pack — "potassium within
            # 90 days" would pass on a lab that does not exist yet. One clock
            # skew or mistyped year and the sufficiency check silently stops
            # asking for the test it exists to demand.
            if obs.taken_at > self.as_of:
                continue
            if best is None or obs.taken_at >= best.taken_at:
                best = obs
        return best

    def previous(self, code: str) -> Observation | None:
        """The observation immediately before the latest one."""
        matches = sorted(
            (o for o in self.observations if o.code == code),
            key=lambda o: o.taken_at,
        )
        return matches[-2] if len(matches) >= 2 else None

    def observation_age_days(self, code: str) -> int | None:
        obs = self.latest(code)
        return None if obs is None else (self.as_of - obs.taken_at).days

    def has_diagnosis_prefix(self, prefix: str) -> bool:
        return any(
            d.code.upper().startswith(prefix.upper())
            for d in self.diagnoses
            if d.status == "active"
        )

    def bp_series(self, limit: int = 6) -> list[tuple[date, float | None, float | None]]:
        """Derived view: the last `limit` paired readings, oldest first."""
        by_date: dict[date, dict[str, float]] = {}
        for o in self.observations:
            if o.code in ("sbp", "dbp"):
                by_date.setdefault(o.taken_at, {})[o.code] = o.value
        rows = [(d, v.get("sbp"), v.get("dbp")) for d, v in sorted(by_date.items())]
        return rows[-limit:]

    def series(self, codes: tuple[str, ...], limit: int = 6
               ) -> list[tuple[date, dict[str, float]]]:
        """The last `limit` visits that recorded any of `codes`, oldest first.

        The generic form of bp_series. A pathway whose target is one HbA1c needs
        the same "how many visits in a row were at target" question answered,
        and it should not need a method named after someone else's measurement.
        """
        by_date: dict[date, dict[str, float]] = {}
        for observation in self.observations:
            if observation.code in codes and observation.taken_at <= self.as_of:
                by_date.setdefault(observation.taken_at, {})[observation.code] = (
                    observation.value
                )
        return sorted(by_date.items())[-limit:]

    def medication_molecules(self) -> set[str]:
        return {m.molecule for m in self.medications}
