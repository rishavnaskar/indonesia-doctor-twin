"""The scripted page: every scenario in tools/scenarios.py, run once.

Separate from run.py because it answers a different question. run.py runs
whatever patients it is handed, which is what /clinic does. This produces the
fixed set the demo opens on, and the counts underneath it.
"""

from __future__ import annotations

import os
from datetime import datetime

from service.gate.checks import catalogue as check_catalogue
from service.packs.loader import load_pack
from service.present.layer import Labels
from service.router.router import default_router
from tools import scenarios as scenario_module
from tools.demo.encounter import NOW, _encounter
from tools.demo.store_access import reset_allowed, store


def _reported_drafter(encounters, fallback: str) -> str:
    """Who actually drafted these encounters, taken from the encounters.

    A resumed run never calls the model, so the backend object still reports its
    *configured* name — `some/model` rather than the `some/model@served_by` a
    hosted backend rewrites itself to once it has an answer. The page would then
    under-report provenance on exactly the runs where the provenance is already
    on file. The encounters are the record of what happened; the live object is
    only this process's configuration, so the record wins.
    """
    for encounter in encounters:
        recorded = ((encounter.get("proposal") or {}).get("provenance") or [None])[0]
        if recorded:
            return recorded
    return fallback


def collect(pack_id: str = "id", router=None, on_progress=None) -> dict:
    """Run every scenario and return the whole page's data.

    `on_progress(done, total, title, outcome)` is called after each encounter.
    A live run makes one model call per scenario and can take minutes on a
    rate-limited free tier; a surface that says nothing for that long is
    indistinguishable from one that has hung.
    """
    rules = load_pack(pack_id)
    labels = Labels.from_pack(rules.language)
    router = router or default_router()

    scenarios = scenario_module.build(rules)
    encounters = []
    for index, scenario in enumerate(scenarios, start=1):
        encounter = _encounter(scenario, rules, labels, router)
        encounters.append(encounter)
        if on_progress:
            on_progress(
                index,
                len(scenarios),
                scenario.title,
                encounter.get("error") or encounter["outcome"],
            )

    reasoner = "rule-following reference reasoner (no AI model)"
    is_model = False
    try:
        reasoner = router.get(router.default).backend.version()
        is_model = True
    except (KeyError, AttributeError):
        pass
    if is_model:
        reasoner = _reported_drafter(encounters, reasoner)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": NOW.isoformat(),
        # Read after the encounters ran, so the counts include them. The page
        # states where this deployment keeps its state, because "durable" is
        # the kind of claim that should be checkable from the thing itself.
        "store": store().summary(),
        # Set by the container. A public deployment says so on the page: this
        # document argues that health data must be processed in-country, and a
        # demo on foreign infrastructure has to answer that rather than hope
        # nobody asks. The answer is that every record here is synthetic and the
        # residency guard structurally refuses anything else.
        "hosted": os.environ.get("CLINICIAN_HOSTED", "") == "1",
        "reset_allowed": reset_allowed(),
        # How many of the encounters below came back from the store rather than
        # being run again. On a second `make live` this is the whole page, and
        # zero model calls.
        "resumed": sum(1 for e in encounters if e.get("resumed")),
        # Every pathway the pack carries, named by the pack. The surface used to
        # hard-code "adult hypertension", which was the first of two and became
        # wrong the moment a second one shipped — above four diabetes encounters.
        "pathways": [
            {"name": name, "label": (rules.pathways[name] or {}).get("label") or name}
            for name in (rules.pathway_order or list(rules.pathways))
        ],
        "pack": {
            "pack_id": rules.pack_id,
            "version": rules.version,
            "review_status": rules.review_status,
            "molecule_count": len(rules.molecules),
            "site_count": len(rules.sites),
            "language": rules.language.get("output_language", ""),
        },
        "reasoner": reasoner,
        "is_model": is_model,
        "glossary": rules.glossary,
        "checks": check_catalogue(),
        "encounters": encounters,
        "declined": sum(1 for e in encounters if not e["committed"] and not e.get("error")),
        "drafter_failures": sum(1 for e in encounters if e.get("error")),
        "total": len(encounters),
    }
