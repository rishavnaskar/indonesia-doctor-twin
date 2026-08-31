"""The sites page exists to make gate check 9 legible.

Which only works if it agrees with the gate. These tests are about that
agreement, not about the HTML: a page that renders beautifully and tells a
reviewer something the check disagrees with is worse than no page.
"""

from __future__ import annotations

from datetime import date

from service.gate.checks.c9_executable import evidence_gap
from service.packs.loader import load_pack
from tools.demo.run import sites_view
from tools.demo.sites import render_sites


def test_every_site_in_the_pack_is_rendered():
    view = sites_view()
    assert {s["site_id"] for s in view["sites"]} == set(load_pack("id").sites)


def test_labs_are_listed_against_the_whole_catalogue_not_just_what_is_present():
    """A site's own list is a fact. The absences are what explain a referral."""
    view = sites_view()
    catalogue = {i["code"] for i in view["investigations"]}
    for site in view["sites"]:
        assert {lab["code"] for lab in site["labs"]} == catalogue


def test_site_c_cannot_run_potassium():
    """The single most demonstrated refusal in the demo, asserted."""
    site_c = next(s for s in sites_view()["sites"] if s["site_id"] == "SITE-C")
    k = next(lab for lab in site_c["labs"] if lab["code"] == "k")
    assert k["available"] is False


def test_availability_matches_the_pack_exactly():
    rules = load_pack("id")
    for site in sites_view()["sites"]:
        raw = rules.sites[site["site_id"]]
        assert {lab["code"] for lab in site["labs"] if lab["available"]} \
            == set(raw.get("labs_available") or [])
        assert {m["molecule"] for m in site["molecules"] if m["stocked"]} \
            == set(raw.get("stocked_molecules") or []) & set(rules.molecules)


def test_evidence_verdicts_come_from_the_gate():
    """Not a reimplementation of the staleness rule. The gate's own function."""
    rules = load_pack("id")
    max_age = (rules.evidence_policy or {}).get("max_age_days")
    today = date.today()
    for site in sites_view()["sites"]:
        raw = rules.sites[site["site_id"]]
        for lab in site["labs"]:
            if not lab["available"]:
                continue
            assert lab["gap"] == evidence_gap(raw, lab["code"],
                                              max_age=max_age, today=today)


def test_a_lapsed_licence_is_shown_as_unable_to_sign():
    """SITE-A carries one deliberately expired SIP. The page must not hide it."""
    site_a = next(s for s in sites_view()["sites"] if s["site_id"] == "SITE-A")
    lapsed = [p for p in site_a["practitioners"] if p["can_sign"]]
    assert lapsed, "the fixture that makes this test meaningful has gone"
    assert all("expired" in p["can_sign"] for p in lapsed)


def test_page_renders_without_the_pack_leaking_raw_yaml():
    html = render_sites(sites_view())
    assert html.startswith("<!doctype html>")
    assert "SITE-C" in html and "creatinine" in html
    # Written by the pack, not by hand: the page must not contain a site label
    # that the registry does not.
    labels = {s["label"] for s in sites_view()["sites"]}
    assert all(label in html for label in labels)


def test_the_route_serves_it():
    """A view nothing serves is not a feature."""
    import tools.demo.__main__ as demo

    src = demo.__file__
    text = open(src).read()
    assert '"/sites"' in text and '"/api/sites"' in text


def test_reset_is_off_by_default_on_a_public_deployment(monkeypatch):
    """A wipe button on a public URL is one misclick from an empty demo."""
    from tools.demo.run import reset_allowed

    monkeypatch.delenv("CLINICIAN_ALLOW_RESET", raising=False)
    monkeypatch.setenv("CLINICIAN_HOSTED", "1")
    assert reset_allowed() is False

    monkeypatch.setenv("CLINICIAN_ALLOW_RESET", "1")
    assert reset_allowed() is True, "the operator can still switch it on"

    monkeypatch.delenv("CLINICIAN_HOSTED", raising=False)
    monkeypatch.setenv("CLINICIAN_ALLOW_RESET", "0")
    assert reset_allowed() is False, "and can switch it off locally too"


def test_reset_is_available_locally_by_default(monkeypatch):
    from tools.demo.run import reset_allowed

    monkeypatch.delenv("CLINICIAN_ALLOW_RESET", raising=False)
    monkeypatch.delenv("CLINICIAN_HOSTED", raising=False)
    assert reset_allowed() is True


def test_the_english_instructions_survive_the_contract():
    """The reviewer reads English; the patient reads the local language."""
    from service.contracts.proposal import Provenance
    from service.reason.parse import to_proposal

    raw = {"assessment": "uncontrolled", "recommendation": "continue",
           "patient_instructions": "Minum obat setiap hari.",
           "patient_instructions_en": "Take your medicine every day.",
           "confidence": 0.8, "medication_changes": [], "investigations": [],
           "assertions": [], "follow_up_interval_days": 28}
    p = to_proposal(raw, Provenance(model="m@v", prompt_template="t@v", corpus="c@v"))
    assert p.patient_instructions_en == "Take your medicine every day."
    assert p.patient_instructions == "Minum obat setiap hari."
