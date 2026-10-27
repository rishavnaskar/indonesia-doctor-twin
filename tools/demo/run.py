"""Run the scenarios and capture everything the surface needs.

Every field on the page comes from here, and everything here comes from a real
`run_encounter`. Nothing is written by hand.

This module is the orchestration only. What it was also doing, and no longer
does, lives next door:

  * store_access.py  the process-wide store and runtime, and reset
  * resume.py        the thread id, and what is already in the store
  * wire.py          encounters, patients and failures as plain JSON
  * history.py       what /clinic ran in earlier sessions
  * catalogue.py     the pack read out for the browser and for /sites

The names below are re-exported from here because callers have always imported
them from `tools.demo.run`, and moving a function is not a reason to break
them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from service.logging import get_logger
from service.packs.loader import load_pack
from service.present.layer import Labels
from service.router.router import default_router
from tools.demo.catalogue import sites_view, vocabulary
from tools.demo.encounter import NOW, _encounter
from tools.demo.history import clear_clinic_history, clinic_history
from tools.demo.resume import VIEW_VERSION
from tools.demo.scripted import collect
from tools.demo.store_access import forced_fresh, reset_allowed, reset_everything, runtime, store
from tools.demo.wire import (
    unreadable_record,
)

__all__ = [
    "MAX_CONCURRENT_ENCOUNTERS",
    "NOW",
    "VIEW_VERSION",
    "clear_clinic_history",
    "clinic_history",
    "collect",
    "compare_sites",
    "forced_fresh",
    "reset_allowed",
    "reset_everything",
    "run_patients",
    "runtime",
    "sites_view",
    "store",
    "vocabulary",
]

log = get_logger(__name__)

# Free tiers are shared pools, so this stays small: the point is to overlap the
# waiting, not to win a race against everyone else on the internet.
MAX_CONCURRENT_ENCOUNTERS = 3


def run_patients(
    wire_patients: list[dict],
    site_id: str = "SITE-A",
    pack_id: str = "id",
    router=None,
    on_progress=None,
    on_step=None,
) -> dict:
    """Run patients the user built or uploaded, through the identical pipeline.

    Deliberately the same `_encounter` the scripted scenarios use. A demo whose
    interactive mode takes a different path through the system is demonstrating
    something other than the system.
    """
    from tools.demo.patients import from_wire
    from tools.scenarios import Scenario

    rules = load_pack(pack_id)
    labels = Labels.from_pack(rules.language)
    # Whether the *caller* named a drafter, captured before the default is
    # applied. The concurrency decision below used to read `router is None`
    # after this line had made that impossible, so every run went wide —
    # including reference-reasoner runs, where three threads buy nothing and
    # cost the deterministic ordering that a restored list is sorted by.
    drafter_named = router is not None
    router = router or default_router()

    if site_id not in rules.sites:
        raise KeyError(f"unknown site {site_id!r}. Known: {sorted(rules.sites)}")
    site = rules.sites[site_id]

    def one(item: tuple[int, dict]) -> dict:
        index, wire = item
        step = (lambda name, i=index: on_step(i, name)) if on_step else None
        try:
            state = from_wire(wire)
        except Exception as exc:  # noqa: BLE001
            # Contained to one visit. Rejecting a whole cohort because one
            # pasted record has a bad age is the same failure already fixed for
            # drafters, and it is worse here: the reader cannot tell which
            # record was the problem.
            encounter = unreadable_record(wire, index, rules, site, exc)
        else:
            scenario = Scenario(
                key=state.patient_id,
                title=f"{state.patient_id} · {state.age}, {state.sex}",
                note=f"Built in the browser, run at {site_id}.",
                state=state,
                site=site,
                watch_for="",
            )
            encounter = _encounter(
                scenario,
                rules,
                labels,
                router,
                on_step=step,
                resume=False,
                # Stored with the encounter so the page can be rebuilt from the
                # store alone. `wire` is the patient exactly as the browser
                # submitted it, which is what makes a restored visit editable
                # and re-runnable rather than a read-only picture of one.
                extra={"origin": "clinic", "site_id": site_id, "wire": wire},
            )
        if on_progress:
            on_progress(
                index,
                len(wire_patients),
                encounter.get("title") or str(index),
                encounter.get("error") or encounter["outcome"],
            )
        return encounter

    # Encounters are independent — separate patients, separate state, no shared
    # mutable anything since the tampering router stopped monkeypatching. Run
    # them together.
    #
    # This is a demo-latency fix and nothing more: measured at up to two minutes
    # per patient against a free reasoning model, three patients sequentially is
    # six minutes of a silent screen. Concurrency is modest because the free
    # tiers are shared pools and hammering one earns a 429 for everybody.
    workers = 1 if not drafter_named else min(MAX_CONCURRENT_ENCOUNTERS, len(wire_patients))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            encounters = list(pool.map(one, enumerate(wire_patients, start=1)))
    else:
        encounters = [one(item) for item in enumerate(wire_patients, start=1)]

    reasoner = "rule-following reference reasoner (no AI model)"
    is_model = False
    try:
        reasoner = router.get(router.default).backend.version()
        is_model = True
    except (KeyError, AttributeError):
        pass

    return {
        "encounters": encounters,
        "reasoner": reasoner,
        "is_model": is_model,
        "declined": sum(1 for e in encounters if not e["committed"] and not e.get("error")),
        "drafter_failures": sum(1 for e in encounters if e["outcome"] == "drafter_failed"),
        "unreadable": sum(1 for e in encounters if e["outcome"] == "unreadable"),
        "residency_refused": sum(1 for e in encounters if e["outcome"] == "residency_refused"),
        "total": len(encounters),
    }


def compare_sites(wire_patients: list[dict], pack_id: str = "id", router=None) -> dict:
    """The same patients at every hospital, side by side.

    The single clearest thing this system does is give two different right
    answers to the same patient depending on where they are standing — ask for
    the test where it can be run, refer where it cannot. Reaching that through a
    dropdown, twice, means most people never see it.
    """
    rules = load_pack(pack_id)
    by_site = {}
    for site_id in rules.sites:
        result = run_patients(wire_patients, site_id=site_id, pack_id=pack_id, router=router)
        by_site[site_id] = {
            e["key"]: {
                "outcome": e["outcome"],
                "band": e["presentation"]["band"],
                "reasons": [f["message"] for f in e["findings"] if f["severity"] == "block"],
                "recommendation": (e["proposal"] or {}).get("recommendation"),
            }
            for e in result["encounters"]
        }
    keys = list(by_site[next(iter(by_site))])
    return {
        "sites": [
            {"site_id": s["site_id"], "label": s.get("label", ""), "tier": s.get("tier", "")}
            for s in rules.sites.values()
        ],
        "patients": keys,
        "by_site": by_site,
        # The rows worth looking at: same patient, different answer.
        "divergent": [
            key for key in keys if len({by_site[s][key]["outcome"] for s in by_site}) > 1
        ],
    }
