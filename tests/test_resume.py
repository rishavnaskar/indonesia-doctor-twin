"""A second run picks up what the first one wrote.

Resumption is what makes the checkpoint load-bearing rather than decorative:
without it the durable runtime stores a record nothing ever reads, and `make
live` pays for nine model calls every time somebody reloads the page.

The risk it introduces is the one every cache has - showing an answer to a
question nobody asked. So most of what is here is about invalidation: the
thread id is derived from everything that could change the answer, and these
tests are the list of what "everything" means.

The two surfaces that resume have their own files, because the rules are one
subject and each surface applying them is another: `test_resume_clinic.py`
and `test_resume_live.py`.
"""

from __future__ import annotations

import pytest

from service.packs.loader import load_pack
from service.router.router import default_router
from tools import scenarios as scenario_module
from tools.demo import resume as demo_resume
from tools.demo import run as demo_run
from tools.demo import scripted as demo_scripted
from tools.demo import store_access


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


@pytest.fixture
def scenario(rules):
    return scenario_module.build(rules)[0]


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """A store of this test's own. Resumption reads whatever is there."""
    monkeypatch.setenv("CLINICIAN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("CLINICIAN_STORE_BACKEND", "files")
    monkeypatch.delenv("CLINICIAN_FRESH", raising=False)
    monkeypatch.setattr(store_access, "_STORE", None)
    monkeypatch.setattr(store_access, "_RUNTIME", None)
    yield


def test_the_second_run_replays_instead_of_re_running(rules, scenario):
    router = default_router()
    first = demo_run._encounter(scenario, rules, _labels(rules), router)
    second = demo_run._encounter(scenario, rules, _labels(rules), router)

    assert first["resumed"] is False
    assert second["resumed"] is True
    assert second["outcome"] == first["outcome"]
    assert second["presentation"] == first["presentation"]
    assert second["signature"] == first["signature"], (
        "a replayed encounter must carry the signature that was actually given, not a fresh one"
    )


def test_a_new_process_resumes_from_what_is_on_disk(rules, scenario):
    """The point of the whole exercise: `make` twice does not re-run `make`."""
    router = default_router()
    demo_run._encounter(scenario, rules, _labels(rules), router)

    # Everything this process holds in memory, dropped.
    store_access._STORE = None
    store_access._RUNTIME = None

    assert demo_run._encounter(scenario, rules, _labels(rules), router)["resumed"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "id-9999-99-99"),
        ("pack_id", "other"),
    ],
)
def test_editing_the_pack_invalidates_the_stored_run(rules, scenario, field, value):
    """Editing a pack file and refreshing has to show the rules moving. A cache
    that survived a guideline change would be showing the old guideline's
    answer under the new guideline's name."""
    router = default_router()
    before = demo_resume.thread_id_for(scenario, rules, router)

    import copy

    edited = copy.copy(rules)
    setattr(edited, field, value)

    assert demo_resume.thread_id_for(scenario, edited, router) != before


def test_a_different_patient_is_a_different_encounter(rules, scenario):
    """/clinic builds patients in the browser, and two of them arrive under the
    same scenario key."""
    import copy

    router = default_router()
    other = copy.copy(scenario)
    other.state = copy.deepcopy(scenario.state)
    other.state.age = scenario.state.age + 1

    assert demo_resume.thread_id_for(other, rules, router) != demo_resume.thread_id_for(
        scenario, rules, router
    )


def test_swapping_the_drafter_invalidates_the_stored_run(rules, scenario):
    """The expensive case. A page drafted by the reference reasoner must never
    be served as though a model had written it."""

    class _Backend:
        model = "some-vendor/some-model"

        def version(self):
            return "some-vendor/some-model@somewhere"

    class _Route:
        backend = _Backend()

    class _Router:
        default = "model"

        def get(self, _name):
            return _Route()

    assert demo_resume.thread_id_for(scenario, rules, _Router()) != demo_resume.thread_id_for(
        scenario, rules, default_router()
    )


def test_the_drafter_key_does_not_move_once_a_model_has_answered(rules, scenario):
    """`version()` on a hosted backend rewrites itself to `model@served_by`
    after its first reply. Keying on that would give the first encounter of a
    run a different id from the second, and nothing would ever resume."""

    class _Backend:
        model = "some-vendor/some-model"

        def __init__(self):
            self._answered = False

        def version(self):
            return (
                "some-vendor/some-model@somewhere" if self._answered else "some-vendor/some-model"
            )

    backend = _Backend()

    class _Route:
        pass

    _Route.backend = backend

    class _Router:
        default = "model"

        def get(self, _name):
            return _Route()

    router = _Router()
    before = demo_resume.thread_id_for(scenario, rules, router)
    backend._answered = True
    assert demo_resume.thread_id_for(scenario, rules, router) == before


def test_fresh_forces_a_re_run(rules, scenario, monkeypatch):
    """Watching a live model disagree with itself across runs is a real thing
    to want, and it is the exact thing resumption otherwise hides."""
    router = default_router()
    demo_run._encounter(scenario, rules, _labels(rules), router)

    monkeypatch.setenv("CLINICIAN_FRESH", "1")
    assert demo_run._encounter(scenario, rules, _labels(rules), router)["resumed"] is False


def test_a_resumed_page_still_reports_its_own_storage(rules):
    """The header states where state lives and how much of it there is. On a
    resumed run those numbers must be the store's, not zero."""
    page = demo_run.collect()
    again = demo_run.collect()

    assert page["resumed"] == 0
    assert again["resumed"] == len(again["encounters"])
    assert again["store"]["encounters_checkpointed"] >= len(again["encounters"])


def _labels(rules):
    from service.present.layer import Labels

    return Labels.from_pack(rules.language)


def test_a_drafter_that_cannot_be_named_does_not_borrow_another_one_s_key(rules, scenario):
    """Failing to name a backend is not itself a name.

    An earlier version returned "reference" whenever the router lookup raised —
    which is exactly how the reference reasoner reports itself. So a router that
    raised for a different reason, such as one that fails every draft, resumed
    the reference reasoner's successful results and the page reported zero
    failures. Caught by an unrelated test, in the suite but not on its own.
    """

    class AlwaysFails:
        default = "model"

        def get(self, *args, **kwargs):
            raise KeyError("no backend")

    assert demo_resume.thread_id_for(scenario, rules, AlwaysFails()) != demo_resume.thread_id_for(
        scenario, rules, default_router()
    )


def test_clinic_runs_fresh_every_time(rules, scenario):
    """A patient built in the browser and run with a button is an action, not a
    report. An action that silently returns an earlier answer looks broken —
    especially on camera, with a live model that was expected to think."""
    router = default_router()
    first = demo_run._encounter(scenario, rules, _labels(rules), router, resume=False)
    second = demo_run._encounter(scenario, rules, _labels(rules), router, resume=False)

    assert first["resumed"] is False
    assert second["resumed"] is False


def test_two_clinic_runs_of_one_patient_are_two_encounters(rules, scenario):
    """Same patient, different times. Sharing a thread id would make the second
    run overwrite the first's checkpoints at the same sequence numbers, and an
    audit trail that loses a run is not one."""
    router = default_router()
    for _ in range(2):
        demo_run._encounter(scenario, rules, _labels(rules), router, resume=False)

    threads = [t for t in demo_run.runtime().threads() if t.startswith(f"DEMO-{scenario.key}-")]
    assert len(threads) == 2


def test_a_resumed_page_reports_who_actually_drafted_it(rules):
    """A resumed run never calls the model, so the backend object still reports
    its *configured* name — a hosted backend only rewrites itself to
    `model@served_by` once it has answered. Taking the page's drafter from the
    live object would under-report provenance on exactly the runs where the
    provenance is already on file."""
    encounters = [{"proposal": {"provenance": ["some/model@somewhere", "p@1", "c@1"]}}]

    assert demo_scripted._reported_drafter(encounters, "some/model") == "some/model@somewhere"
    # Nothing on file: the live object is all there is.
    assert demo_scripted._reported_drafter([{"proposal": None}], "some/model") == "some/model"
