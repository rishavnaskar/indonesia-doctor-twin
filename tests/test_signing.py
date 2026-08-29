"""The signature line is enforced, not documented."""

from datetime import date, datetime

import pytest

from datagen.proposer import propose
from datagen.synthetic import make_patient
from service.packs.loader import load_pack
from service.signing import AuditLog, SignatureRefused, Signer, sign

WHEN = datetime(2026, 8, 29, 10, 30)


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


@pytest.fixture()
def proposal(rules):
    state = make_patient(1, controlled=True)
    return propose(state, rules)


def test_a_licensed_practitioner_can_sign(rules, proposal):
    audit = AuditLog()
    record = sign(rules.sites["SITE-A"], Signer("PRAC-A-001", True), proposal,
                  "accepted", WHEN, audit)
    assert record.practitioner_id == "PRAC-A-001"
    assert len(audit.records) == 1
    # The record must be able to answer "what exactly did they sign?"
    assert all(record.proposal_provenance)


def test_an_expired_licence_is_refused(rules, proposal):
    """PRAC-A-003's licence lapsed in February. Legally this is an unsigned script."""
    with pytest.raises(SignatureRefused, match="expired"):
        sign(rules.sites["SITE-A"], Signer("PRAC-A-003", True), proposal,
             "accepted", WHEN, AuditLog())


def test_someone_not_on_this_site_roster_is_refused(rules, proposal):
    with pytest.raises(SignatureRefused, match="not on the roster"):
        sign(rules.sites["SITE-A"], Signer("PRAC-B-001", True), proposal,
             "accepted", WHEN, AuditLog())


def test_an_unauthenticated_signer_is_refused(rules, proposal):
    with pytest.raises(SignatureRefused):
        sign(rules.sites["SITE-A"], Signer("PRAC-A-001", False), proposal,
             "accepted", WHEN, AuditLog())


def test_an_unpinned_proposal_cannot_be_signed(rules, proposal):
    from service.contracts.proposal import Provenance

    proposal.provenance = Provenance(model="", prompt_template="p@1", corpus="c@1")
    with pytest.raises(SignatureRefused, match="unpinned"):
        sign(rules.sites["SITE-A"], Signer("PRAC-A-001", True), proposal,
             "accepted", WHEN, AuditLog())


def test_rejection_reasons_are_captured(rules, proposal):
    """Reject reasons are the most valuable telemetry in the system."""
    audit = AuditLog()
    sign(rules.sites["SITE-A"], Signer("PRAC-A-001", True), proposal, "rejected",
         WHEN, audit, rejection_reason="disagree_with_target")
    assert audit.records[0].rejection_reason == "disagree_with_target"
