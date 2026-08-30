"""Read-only tools the drafter may call, instead of being handed everything.

Today the prompt pre-loads the whole formulary, the guideline and the site
registry. That works because the pack is eleven molecules and one pathway. It
does not survive a real formulary, and it never survives a second pathway — the
prompt would become mostly material irrelevant to the patient in front of it.

There is a second reason, and for a safety argument it is the better one: **what
the model asks for is evidence.** A drafter that titrates a RAAS-acting drug
without ever requesting a potassium result has told us something no output
inspection would reveal. The requests are recorded on the proposal for exactly
that.

Every tool is read-only and pure. There is no tool that writes, prescribes,
orders, sends or schedules — not because the model is not trusted with them
(though it is not), but because a tool that changes the world outside this
process is an action, and every action in this system goes through the gate and
a signature. A model that could act would be routing around both.

The tools serve pack and state data only. Nothing here reaches a network, a
database or a file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

MAX_CALLS = 8


def tool_specs(rules) -> list[dict[str, Any]]:
    """OpenAI-compatible tool definitions, built from the pack.

    The enumerations come from the pack for the usual reason: /service may not
    name a drug or a test, and a hard-coded list here would go stale the moment
    the formulary changed.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "get_measurement",
                "description": (
                    "Look up one of this patient's recorded measurements, with how "
                    "many days old it is. Returns not_recorded if there is none."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "enum": sorted(rules.investigations)
                                 + ["sbp", "dbp"]},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_drug",
                "description": (
                    "Dosing limits, class and restrictions for one prescribable drug."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "molecule": {"type": "string", "enum": sorted(rules.molecules)},
                    },
                    "required": ["molecule"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_site_capability",
                "description": (
                    "What this hospital can actually do today: which tests it runs "
                    "and which drugs it stocks."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_history",
                "description": "This patient's earlier visits, most recent first.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


@dataclass
class Toolbox:
    """Executes tool calls against the state and the pack. Nothing else."""

    state: Any
    rules: Any
    site: dict[str, Any] | None = None
    requested: list[str] = field(default_factory=list)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        self.requested.append(name)
        handler = {
            "get_measurement": self._measurement,
            "get_drug": self._drug,
            "get_site_capability": self._capability,
            "get_history": self._history,
        }.get(name)
        if handler is None:
            # Never guessed at. A model inventing a tool name is a fact worth
            # surfacing, not smoothing over.
            return json.dumps({"error": f"no such tool: {name}"})
        try:
            return json.dumps(handler(arguments or {}), default=str)
        except Exception as exc:  # noqa: BLE001 - reported to the model, never raised
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    def _measurement(self, args: dict) -> dict:
        code = str(args.get("code") or "")
        observation = self.state.latest(code)
        if observation is None:
            return {"code": code, "status": "not_recorded"}
        return {
            "code": code,
            "value": observation.value,
            "unit": observation.unit,
            "age_days": self.state.observation_age_days(code),
            "source": observation.source.value,
        }

    def _drug(self, args: dict) -> dict:
        name = str(args.get("molecule") or "")
        molecule = self.rules.molecules.get(name)
        if molecule is None:
            return {"molecule": name, "status": "not_prescribable_here"}
        return {
            "molecule": molecule.molecule,
            "drug_class": molecule.drug_class,
            "forms_mg": molecule.forms_mg,
            "dosing": molecule.dosing,
            "restrictions": molecule.restrictions,
            "citation": molecule.citation,
        }

    def _capability(self, _args: dict) -> dict:
        site = self.site or {}
        return {
            "site_id": site.get("site_id"),
            "labs_available": sorted(site.get("labs_available") or []),
            "stocked_molecules": sorted(site.get("stocked_molecules") or []),
            "as_of": site.get("as_of"),
        }

    def _history(self, _args: dict) -> dict:
        return {
            "encounters": [
                {"date": e.encounter_date.isoformat(), "sbp": e.sbp, "dbp": e.dbp,
                 "decision": e.decision}
                for e in sorted(self.state.encounters,
                                key=lambda e: e.encounter_date, reverse=True)
            ]
        }
