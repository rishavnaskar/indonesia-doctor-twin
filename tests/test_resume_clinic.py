"""Resumption as /clinic experiences it: across sessions, not within one.

The claim on the page is that patients you generate and run come back the next
time you open it, with their verdicts, and that clearing the list deletes
nothing. The store refuses UPDATE and DELETE, so "clear" writes a marker
forward and the page starts reading after it - which is only correct if a run
made afterwards shows up again. That pair is what these tests hold.

The thread-id rules they rest on are in `test_resume.py`.
"""

from __future__ import annotations

import pytest

from service.packs.loader import load_pack
from tools import scenarios as scenario_module
from tools.demo import run as demo_run
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


def _run_clinic(n=2, seed=5):
    from tools.demo.patients import generate
    from tools.demo.run import run_patients

    return run_patients(generate(n, seed=seed, profile="clean"), site_id="SITE-A")


def test_clinic_visits_come_back_in_a_later_session():
    """The interactive page was the one part of the system that kept nothing:
    results in a dict in the server process, patients in the browser tab. Both
    were being written to the store the whole time — nothing read them back."""
    ran = _run_clinic()

    store_access._STORE = None  # a new server process
    store_access._RUNTIME = None

    restored = demo_run.clinic_history()
    assert {v["key"] for v in restored} == {e["key"] for e in ran["encounters"]}
    # Newest first, so the last thing you did is the first thing you see.
    assert [v["ran_at"] for v in restored] == sorted((v["ran_at"] for v in restored), reverse=True)
    assert all(v["outcome"] for v in restored)
    assert all(v["signature"] or v["outcome"] != "committed" for v in restored)


def test_a_restored_visit_carries_the_record_it_was_built_from():
    """Restoring a picture of a verdict is not much use. The wire record is what
    makes a restored visit editable and re-runnable."""
    _run_clinic(n=1)

    visit = demo_run.clinic_history()[0]
    assert visit["wire"], "the submitted record must be stored with the encounter"
    assert visit["wire"]["patient_id"] == visit["key"]
    assert visit["site_id"] == "SITE-A"


def test_the_scripted_page_does_not_leak_into_the_clinic_list():
    demo_run.collect()
    assert demo_run.clinic_history() == []


def test_only_the_newest_run_of_a_patient_is_listed():
    """Re-running a record is the same patient seen again, not a second
    patient. Both runs stay on the record; only one gets a card."""
    _run_clinic(n=1)
    _run_clinic(n=1)

    listed = demo_run.clinic_history()
    assert len(listed) == 1
    threads = [t for t in demo_run.runtime().threads() if t.startswith("DEMO-SYN-")]
    assert len(threads) == 2, "both runs must still be on the record"


def test_clearing_hides_the_list_without_deleting_anything():
    """The store refuses UPDATE and DELETE, so clearing is a marker written
    forward rather than history rewritten backwards. An audit log with a clear
    button that worked would not be an audit log."""
    _run_clinic()
    assert demo_run.clinic_history()

    demo_run.clear_clinic_history()
    assert demo_run.clinic_history() == []

    stored = [
        e
        for history in demo_run.runtime().checkpoints.values()
        for e in history
        if e.step == "rendered" and isinstance(e.state, dict) and e.state.get("origin") == "clinic"
    ]
    assert stored, "the visits must still be on the record after a clear"


def test_a_run_after_a_clear_shows_up_again():
    _run_clinic(n=1, seed=1)
    demo_run.clear_clinic_history()
    _run_clinic(n=1, seed=2)

    assert len(demo_run.clinic_history()) == 1
