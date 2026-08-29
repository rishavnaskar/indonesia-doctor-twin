"""What the patient would actually be taking if this proposal were signed.

Every drug-safety question is about the *resulting* regimen, not about the
change in isolation. "Start candesartan" is safe or unsafe depending entirely on
what else is already on the list — which is the whole reason a per-drug checker
misses ACEi+ARB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from service.contracts.proposal import ChangeAction

if TYPE_CHECKING:  # pragma: no cover
    from service.contracts.proposal import Proposal
    from service.packs.loader import RuleSet
    from service.state.models import PatientState

RAAS_CLASSES = ("acei", "arb", "mra")


@dataclass(frozen=True)
class RegimenDrug:
    molecule: str
    mg_per_dose: float | None
    doses_per_day: int | None
    changed: bool

    @property
    def mg_daily(self) -> float | None:
        if self.mg_per_dose is None or self.doses_per_day is None:
            return None
        return self.mg_per_dose * self.doses_per_day


def resulting_regimen(state: "PatientState", proposal: "Proposal") -> dict[str, RegimenDrug]:
    regimen: dict[str, RegimenDrug] = {
        m.molecule: RegimenDrug(m.molecule, m.mg_per_dose, m.doses_per_day, changed=False)
        for m in state.medications
    }

    for change in proposal.medication_changes:
        if change.action is ChangeAction.STOP:
            regimen.pop(change.molecule, None)
            continue

        existing = regimen.get(change.molecule)
        mg = change.mg_per_dose if change.mg_per_dose is not None else (
            existing.mg_per_dose if existing else None
        )
        per_day = change.doses_per_day if change.doses_per_day is not None else (
            existing.doses_per_day if existing else None
        )
        regimen[change.molecule] = RegimenDrug(change.molecule, mg, per_day, changed=True)

    return regimen


def classes_in(regimen: dict[str, RegimenDrug], rules: "RuleSet") -> dict[str, list[str]]:
    """drug_class -> molecules present in that class."""
    by_class: dict[str, list[str]] = {}
    for molecule in regimen:
        cls = rules.drug_class_of(molecule)
        if cls:
            by_class.setdefault(cls, []).append(molecule)
    return by_class


def patient_classes(state: "PatientState", rules: "RuleSet") -> set[str]:
    """Classes the patient is already on, including ones we never prescribe.

    A patient can arrive taking an NSAID bought over the counter. It is not in
    our formulary and never will be, but the interaction rules still have to see
    it — which is why unknown molecules fall back to a declared class rather
    than being dropped.
    """
    classes: set[str] = set()
    for med in state.medications:
        cls = rules.drug_class_of(med.molecule)
        if cls:
            classes.add(cls)
    return classes


def touches_raas(regimen: dict[str, RegimenDrug], rules: "RuleSet") -> bool:
    return any(
        rules.drug_class_of(d.molecule) in RAAS_CLASSES
        for d in regimen.values()
        if d.changed
    )
