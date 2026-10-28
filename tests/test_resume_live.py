"""Resumption as `python -m tools.live` experiences it.

`make live` has two stages that call a model, and both must key on the same
things the surface keys on or the second run still spends. That is the bug
this file exists to stop coming back.

The thread-id rules it rests on are in `test_resume.py`.
"""

from __future__ import annotations

import pytest

from service.packs.loader import load_pack
from tools import scenarios as scenario_module
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


def _live_args(**over):
    import argparse

    return argparse.Namespace(
        **{"samples": 1, "critic": False, "tools": False, "shadow": False, **over}
    )


def test_the_live_runner_keys_on_the_same_things_the_surface_does(rules):
    """`make live` has two stages that call a model. Both must resume, or the
    second run still spends — which is the bug this pair of tests exists to
    stop coming back."""
    from datagen.synthetic import make_patient
    from tools import live

    site = rules.sites["SITE-A"]
    state = make_patient(900, controlled=True)
    base = live._thread_id(state, rules, site, "some/model", _live_args())

    assert base == live._thread_id(state, rules, site, "some/model", _live_args())
    assert base != live._thread_id(state, rules, site, "other/model", _live_args())
    assert base != live._thread_id(state, rules, rules.sites["SITE-C"], "some/model", _live_args())


@pytest.mark.parametrize("option", ["samples", "critic", "tools", "shadow"])
def test_a_sampling_option_is_a_different_question(rules, option):
    """A draft agreed by three samples and checked by a critic is not the draft
    one call produced. Serving one for the other would misreport what was run."""
    from datagen.synthetic import make_patient
    from tools import live

    site, state = rules.sites["SITE-A"], make_patient(900, controlled=True)
    changed = {"samples": 3} if option == "samples" else {option: True}

    assert live._thread_id(state, rules, site, "m", _live_args()) != live._thread_id(
        state, rules, site, "m", _live_args(**changed)
    )


def test_only_a_finished_live_encounter_is_replayable(rules):
    """A response that did not parse is not an answer. Storing it would replay
    a failure forever and never retry the call that might succeed."""
    from service.graph.runtime import InMemoryRuntime
    from tools import live

    runtime = InMemoryRuntime()
    runtime.start("L1", {"a": 1})
    assert live._stored(runtime, "L1") is None, "only a 'rendered' entry counts"

    runtime.checkpoint(
        "L1", "rendered", {"origin": "live", "outcome": "committed", "lines": ["      coded: I10"]}
    )
    assert live._stored(runtime, "L1")["outcome"] == "committed"


def test_fresh_bypasses_the_live_runner_too(rules, monkeypatch):
    from service.graph.runtime import InMemoryRuntime
    from tools import live

    runtime = InMemoryRuntime()
    runtime.start("L2", {"a": 1})
    runtime.checkpoint("L2", "rendered", {"origin": "live", "outcome": "committed", "lines": []})
    assert live._stored(runtime, "L2") is not None

    monkeypatch.setenv("CLINICIAN_FRESH", "1")
    assert live._stored(runtime, "L2") is None


def test_a_surface_encounter_is_not_replayed_as_a_live_one(rules):
    """Both write 'rendered' checkpoints. Reading one as the other would print
    a scripted-page result under a heading claiming a real model produced it."""
    from service.graph.runtime import InMemoryRuntime
    from tools import live

    runtime = InMemoryRuntime()
    runtime.start("L3", {"a": 1})
    runtime.checkpoint("L3", "rendered", {"origin": "clinic", "outcome": "committed"})
    assert live._stored(runtime, "L3") is None


def test_pack_edit_invalidates_the_thread_id(tmp_path):
    """A pack edit must change the id even when nobody bumps the version.

    `version` is hand-written, so keying resumption on it means an edited
    guideline can replay an answer that predates the edit. The digest is what
    actually makes the claim in the README true.
    """
    import shutil

    from service.packs.loader import PACKS_ROOT, load_pack

    root = tmp_path / "packs"
    shutil.copytree(PACKS_ROOT, root)
    before = load_pack("id", root=root)

    target = root / "id" / "glossary.yaml"
    target.write_text(target.read_text() + "\n# an edit nobody recorded\n")
    after = load_pack("id", root=root)

    assert before.version == after.version, "the declared version is untouched"
    assert before.content_digest != after.content_digest
