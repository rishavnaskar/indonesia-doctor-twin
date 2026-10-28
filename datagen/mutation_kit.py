"""The vocabulary a planted error is written in.

`adversarial.py` is the catalogue: eighteen specific ways a proposal can be
wrong. This is what each entry is written with - what a broken case *is*, and
the four moves that make one. Keeping them apart means a new mutation is a
single function appended to a list, with nothing to read first except this
file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from datagen.synthetic import TODAY, _obs, make_patient
from service.contracts.proposal import ChangeAction, MedicationChange


@dataclass
class BrokenCase:
    name: str
    state: object
    proposal: object
    site_id: str
    expected_rules: set[str]
    description: str


def _uncontrolled(seed):
    return make_patient(seed, controlled=False)


def _controlled(seed):
    return make_patient(seed, controlled=True)


def _set_obs(state, code, value, days_ago=0):
    state.observations = [
        o
        for o in state.observations
        if not (o.code == code and o.taken_at == TODAY - timedelta(days=days_ago))
    ]
    state.observations.append(_obs(code, value, days_ago))
    return state


def _change(
    molecule, mg, per_day, action=ChangeAction.START, citation="fornas-prb-2025-12-31#amlodipine"
):
    return MedicationChange(
        action=action,
        molecule=molecule,
        mg_per_dose=mg,
        doses_per_day=per_day,
        rationale="planted error",
        citation=citation,
    )
