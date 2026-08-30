"""Structural conformance of the outbound bundle.

**This is not the official HL7 validator.** It checks the R4 invariants that can
be checked without one — required fields, cardinality, transaction-entry rules,
identifier syntax, reference resolution. Running the authoritative validator
needs its Java distribution and is the right next step before a real
submission; what this catches is the class of error that would otherwise be
found by a server rejecting the transaction, which is the worst place to find it.

It found one: every entry's `fullUrl` read `urn:uuid:ENC-1`, and the part after
`urn:uuid:` has to be an actual UUID.
"""

from __future__ import annotations

import json
import re

import pytest

from datagen.synthetic import make_patient
from service.emit.coding import build_claim
from service.emit.fhir import build_bundle
from service.packs.loader import load_pack
from service.reason import reference

UUID_URN = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# R4 minimum cardinality for the resources this bundle emits.
REQUIRED = {
    "Encounter": ["status", "class"],
    "Condition": ["subject"],
    "Observation": ["status", "code"],
    "MedicationRequest": ["status", "intent", "subject"],
}


@pytest.fixture(scope="module")
def rules():
    return load_pack("id")


@pytest.fixture(scope="module")
def payload(rules):
    site = rules.sites["SITE-A"]
    state = make_patient(101, controlled=False)
    proposal = reference.propose(state, rules, site)
    return build_bundle(state, build_claim(state, rules), proposal, site,
                        "PRAC-A-001", rules, encounter_id="ENC-1").payload


def _entries(payload):
    return payload.get("entry", [])


def test_it_is_a_transaction_bundle(payload):
    assert payload["resourceType"] == "Bundle"
    assert payload["type"] == "transaction"
    assert _entries(payload)


def test_every_transaction_entry_carries_a_request(payload):
    """Bundle inv-3. Without it the server has no verb to apply."""
    for index, entry in enumerate(_entries(payload)):
        assert entry.get("request", {}).get("method"), f"entry[{index}]"
        assert entry.get("request", {}).get("url"), f"entry[{index}]"


def test_every_full_url_is_a_real_uuid_urn(payload):
    """`urn:uuid:ENC-1` is not a UUID. A validating server rejects the whole
    transaction, and it does so at submission — the worst place to find out."""
    for index, entry in enumerate(_entries(payload)):
        assert UUID_URN.match(entry.get("fullUrl", "")), \
            f"entry[{index}] fullUrl {entry.get('fullUrl')!r}"


def test_full_urls_are_unique_within_the_bundle(payload):
    urls = [e["fullUrl"] for e in _entries(payload)]
    assert len(set(urls)) == len(urls)


def test_full_urls_are_stable_across_rebuilds(rules):
    """Every write is replayed after a connectivity gap. A fullUrl that changed
    between attempts would make two submissions of one encounter look like two
    encounters — the duplicate the offline design exists to prevent."""
    site = rules.sites["SITE-A"]
    state = make_patient(101, controlled=False)

    def build():
        proposal = reference.propose(state, rules, site)
        return [e["fullUrl"] for e in build_bundle(
            state, build_claim(state, rules), proposal, site, "PRAC-A-001",
            rules, encounter_id="ENC-1").payload["entry"]]

    assert build() == build()


def test_a_put_url_matches_the_resource_it_carries(payload):
    for index, entry in enumerate(_entries(payload)):
        if entry["request"]["method"] != "PUT":
            continue
        resource = entry["resource"]
        assert entry["request"]["url"] == \
            f"{resource['resourceType']}/{resource['id']}", f"entry[{index}]"


def test_required_fields_are_present_on_every_resource(payload):
    for index, entry in enumerate(_entries(payload)):
        resource = entry["resource"]
        for field in REQUIRED.get(resource["resourceType"], []):
            assert field in resource, \
                f"entry[{index}] {resource['resourceType']} missing {field}"


def test_a_medication_request_names_a_medication(payload):
    for entry in _entries(payload):
        resource = entry["resource"]
        if resource["resourceType"] != "MedicationRequest":
            continue
        assert any(k in resource for k in
                   ("medicationCodeableConcept", "medicationReference"))


# Elements that are a bare Coding rather than a CodeableConcept, so they carry
# `system`/`code` directly instead of nesting under `coding`. The first version
# of this test only walked `coding` arrays and therefore missed Encounter.class
# — which was one of the two elements actually missing a system.
_BARE_CODING = {"class"}


def test_every_coding_declares_its_system(payload):
    """A code without a system is a string, and a string is not interoperable.

    Both bindings this bundle uses — ActEncounterCode on Encounter.class and
    condition-clinical on Condition.clinicalStatus — are *required* in R4, so
    the system is not optional decoration."""
    problems = []

    def walk(node, path="root"):
        if isinstance(node, dict):
            for coding in node.get("coding", []) or []:
                if "system" not in coding:
                    problems.append(f"{path}.coding: {coding}")
            for key, value in node.items():
                if key in _BARE_CODING and isinstance(value, dict) and "code" in value:
                    if "system" not in value:
                        problems.append(f"{path}.{key}: {value}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(json.loads(json.dumps(payload, default=str)))
    assert not problems, problems


def test_the_only_unresolved_references_are_the_ones_we_never_create(payload):
    """Patient, Practitioner and Organization are referenced but not created,
    which is legal in a transaction — the server is expected to hold them
    already. It is an integration assumption rather than a bug, and it is
    recorded here so it cannot become a surprise at submission: on an empty
    sandbox these three must be seeded first.

    Anything else dangling would be a bug."""
    created = {f"{e['resource']['resourceType']}/{e['resource']['id']}"
               for e in _entries(payload)}
    dangling = set()

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("reference")
            if isinstance(ref, str) and "/" in ref and ref not in created:
                dangling.add(ref.split("/", 1)[0])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(json.dumps(payload, default=str)))
    assert dangling <= {"Patient", "Practitioner", "Organization"}, dangling
