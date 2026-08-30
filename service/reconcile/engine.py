"""SPEC-V1 §5.3 RECONCILE — the deterministic half.

What the record says, against what the patient says. The rule is one line and
the whole module exists to honour it: **discrepancies are surfaced, never
silently resolved.**

That is not caution, it is the only defensible behaviour. Both sources are
routinely wrong in different ways — a record goes stale the moment a patient
buys something at a pharmacy, and a patient misremembers a dose — so a system
that picks a winner is guessing, and it is guessing about what someone is
currently swallowing. Neither source is overwritten here. A patient saying they
stopped a drug does not remove it from the record; it produces a line the
clinician reads.

The comparison needs no model. `source` is mandatory on every medication, so
record-sourced and patient-reported entries can simply be compared. Matching
free text like "the little white one" to a molecule is the part that needs a
model, and it is not done here.

Nothing under /service names a drug or a country: the phrasing and the mapping
from an intake answer to a drug class both come from the pack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from service.state.models import Source

# Sources that represent "what the hospital has on file" rather than "what the
# patient told us today".
_RECORD_SOURCES = (Source.EMR, Source.CLINICIAN_ENTERED, Source.DERIVED)


@dataclass(frozen=True)
class Discrepancy:
    kind: str
    text: str
    gloss: str = ""
    molecule: str | None = None
    drug_class: str | None = None
    record_says: str = ""
    patient_says: str = ""
    # Molecules already on the record whose class interacts with the class this
    # discrepancy implicates. Computed from the pack's own interaction rules, so
    # a clinician sees "this matters *because*" rather than a bare note.
    interacts_with: tuple[str, ...] = ()
    # Whether this could change what a draft should say. Material discrepancies
    # are the ones worth interrupting for.
    material: bool = False


@dataclass
class Reconciliation:
    discrepancies: list[Discrepancy] = field(default_factory=list)

    @property
    def material(self) -> list[Discrepancy]:
        return [d for d in self.discrepancies if d.material]

    def __bool__(self) -> bool:
        return bool(self.discrepancies)


def _phrasing(rules) -> dict[str, Any]:
    return ((rules.language or {}).get("reconciliation")) or {}


def _interacting(rules, drug_class: str | None, record_molecules: list[str]) -> tuple[str, ...]:
    """Which recorded drugs interact with this class, per the pack's own rules."""
    if not drug_class:
        return ()
    classes_at_risk: set[str] = set()
    for rule in rules.interactions:
        pair = list(rule.get("classes") or [])
        if drug_class in pair:
            classes_at_risk |= {c for c in pair if c != drug_class}
    if not classes_at_risk:
        return ()
    return tuple(
        molecule for molecule in record_molecules
        if rules.drug_class_of(molecule) in classes_at_risk
    )


def reconcile(state, rules, intake=None) -> Reconciliation:
    """Compare the record against what the patient said. Change neither."""
    phrasing = _phrasing(rules)
    derived = phrasing.get("derived") or {}

    record = [m for m in state.medications if m.source in _RECORD_SOURCES]
    reported = [m for m in state.medications if m.source is Source.PATIENT_REPORTED]
    record_molecules = [m.molecule for m in record]

    found: list[Discrepancy] = []

    # ---- medication list against medication list --------------------------
    by_molecule = {m.molecule: m for m in record}
    for entry in reported:
        counterpart = by_molecule.get(entry.molecule)
        if counterpart is None:
            spec = derived.get("not_in_record") or {}
            found.append(Discrepancy(
                kind="not_in_record",
                text=spec.get("text", ""), gloss=spec.get("gloss", ""),
                molecule=entry.molecule,
                drug_class=rules.drug_class_of(entry.molecule),
                record_says="not on the record",
                patient_says=f"{entry.molecule} {entry.mg_daily:g} mg daily",
                interacts_with=_interacting(
                    rules, rules.drug_class_of(entry.molecule), record_molecules),
                material=True,
            ))
        elif abs(counterpart.mg_daily - entry.mg_daily) > 1e-6:
            spec = derived.get("dose_differs") or {}
            found.append(Discrepancy(
                kind="dose_differs",
                text=spec.get("text", ""), gloss=spec.get("gloss", ""),
                molecule=entry.molecule,
                drug_class=rules.drug_class_of(entry.molecule),
                record_says=f"{counterpart.mg_daily:g} mg daily",
                patient_says=f"{entry.mg_daily:g} mg daily",
                material=True,
            ))

    # Only meaningful when the patient actually listed something. Silence is not
    # a report that they take nothing.
    if reported:
        reported_molecules = {m.molecule for m in reported}
        for entry in record:
            if entry.molecule not in reported_molecules:
                spec = derived.get("missing_from_report") or {}
                found.append(Discrepancy(
                    kind="missing_from_report",
                    text=spec.get("text", ""), gloss=spec.get("gloss", ""),
                    molecule=entry.molecule,
                    drug_class=rules.drug_class_of(entry.molecule),
                    record_says=f"{entry.molecule} {entry.mg_daily:g} mg daily",
                    patient_says="not mentioned",
                    material=True,
                ))

    # ---- the bounded interview's answers ----------------------------------
    answers = dict(getattr(intake, "answers", {}) or {})
    for field_name in ("adherence", "outside_medication"):
        value = answers.get(field_name)
        if not value or value == "none":
            continue
        spec = (phrasing.get(field_name) or {}).get(value)
        if not spec:
            continue
        drug_class = spec.get("implicates_class")
        found.append(Discrepancy(
            kind=spec.get("kind", field_name),
            text=spec.get("text", ""), gloss=spec.get("gloss", ""),
            drug_class=drug_class,
            record_says="",
            patient_says=str(value),
            interacts_with=_interacting(rules, drug_class, record_molecules),
            material=bool(spec.get("material", False)) or bool(drug_class),
        ))

    return Reconciliation(discrepancies=found)
