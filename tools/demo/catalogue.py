"""What the pack knows, read out for the browser and for /sites.

Both views are read from the pack rather than written into a page, for the same
reason everything else clinical is: a drug list, a symptom set and a site roster
are national vocabulary, and hard-coding them in JavaScript would put the
country back into the engine by the back door.
"""

from __future__ import annotations

import os
from datetime import date

from service.gate.checks import catalogue as check_catalogue
from service.gate.checks.c9_executable import evidence_gap
from service.packs.loader import load_pack
from service.signing import SignatureRefused, Signer, verify_signer
from tools.demo.store_access import reset_allowed


def vocabulary(pack_id: str = "id") -> dict:
    """What the browser needs to build a patient form.

    Read from the pack rather than written into the page, for the same reason
    everything else clinical is: a drug list, a symptom set and a site roster are
    national vocabulary, and hard-coding them in JavaScript would put the country
    back into the engine by the back door.
    """
    rules = load_pack(pack_id)
    glossary = rules.glossary
    return {
        "molecules": [
            {
                "molecule": name,
                "drug_class": mol.drug_class,
                "forms_mg": mol.forms_mg,
                "label": (glossary.get("drug_classes") or {})
                .get(mol.drug_class, {})
                .get("label", ""),
            }
            for name, mol in sorted(rules.molecules.items())
        ],
        "sites": [
            {
                "site_id": s["site_id"],
                "label": s.get("label", ""),
                "tier": s.get("tier", ""),
                "labs_available": sorted(s.get("labs_available") or []),
                "stocked": sorted(s.get("stocked_molecules") or []),
            }
            for s in rules.sites.values()
        ],
        "symptoms": [
            {"code": k, "plain": v} for k, v in sorted((glossary.get("symptoms") or {}).items())
        ],
        "flags": [
            {"code": k, "plain": v} for k, v in sorted((glossary.get("flags") or {}).items())
        ],
        "observations": [
            {
                "code": k,
                "label": v.get("label", k),
                "unit": v.get("unit", ""),
                "plain": v.get("plain", ""),
            }
            for k, v in (glossary.get("observations") or {}).items()
        ],
        "diagnoses": glossary.get("diagnoses") or {},
        "hosted": os.environ.get("CLINICIAN_HOSTED", "") == "1",
        "reset_allowed": reset_allowed(),
        # Grouped, because a flat list of fifteen gives no sense of which ones
        # are supposed to produce a draft and which are supposed to refuse.
        "profiles": [
            {"key": "clean", "label": "Blood pressure · in scope, should draft"},
            {"key": "polypharmacy", "label": "Blood pressure · already on three drugs"},
            {
                "key": "acei_intolerant",
                "label": "Blood pressure · documented ACE-inhibitor intolerance",
            },
            {"key": "no_target", "label": "Blood pressure · group whose target is not extracted"},
            {"key": "stale_labs", "label": "Blood pressure · labs months out of date"},
            {"key": "hyperkalaemia", "label": "Blood pressure · potassium too high"},
            {"key": "red_flag", "label": "Blood pressure · red flag present"},
            {"key": "excluded_pregnancy", "label": "Blood pressure · pregnant"},
            {"key": "excluded_minor", "label": "Blood pressure · under 18"},
            {"key": "excluded_renal", "label": "Blood pressure · severe kidney impairment"},
            {"key": "excluded_secondary", "label": "Blood pressure · secondary hypertension"},
            {"key": "excluded_resistant", "label": "Blood pressure · resistant hypertension"},
            {"key": "excluded_first_presentation", "label": "Blood pressure · first presentation"},
            {"key": "dm:clean", "label": "Diabetes · in scope, should draft"},
            {"key": "dm:no_target", "label": "Diabetes · group whose target is not extracted"},
            {"key": "dm:stale_labs", "label": "Diabetes · HbA1c months out of date"},
            {"key": "dm:red_flag", "label": "Diabetes · red flag present"},
            {"key": "dm:excluded_insulin", "label": "Diabetes · already on insulin"},
            {"key": "dm:excluded_renal", "label": "Diabetes · severe kidney impairment"},
        ],
        "pack": {
            "pack_id": rules.pack_id,
            "version": rules.version,
            "language": rules.language.get("output_language", ""),
        },
        "glossary": glossary,
        "checks": check_catalogue(),
    }


def _can_sign(site, practitioner, when) -> str | None:
    """None if this practitioner could sign here today, else why not."""
    try:
        verify_signer(
            site, Signer(practitioner_id=practitioner["practitioner_id"], authenticated=True), when
        )
    except SignatureRefused as refusal:
        return str(refusal)
    return None


def sites_view(pack_id: str = "id") -> dict:
    """Every site the registry knows, and what each can actually do.

    Exists because gate check 9 is the least legible thing the demo does. A
    reader watching SITE-C refuse a plan is told the site cannot run the assay,
    and has no way to see that for themselves, so the most interesting refusal
    in the system reads as an assertion rather than a consequence.

    Everything here is read from the pack. The staleness verdicts come from the
    gate's own `evidence_gap`, so the page cannot tell a reviewer something the
    check disagrees with.
    """
    rules = load_pack(pack_id)
    catalogue = rules.investigations or {}
    prescribable = sorted(rules.molecules)
    max_age = (rules.evidence_policy or {}).get("max_age_days")
    today = date.today()

    sites = []
    for site in rules.sites.values():
        labs = set(site.get("labs_available") or [])
        stocked = set(site.get("stocked_molecules") or [])
        sites.append(
            {
                "site_id": site["site_id"],
                "label": site.get("label", ""),
                "tier": site.get("tier", ""),
                "service_group": site.get("service_group", ""),
                "continuous_24h": bool((site.get("hours") or {}).get("continuous_24h")),
                "as_of": site.get("as_of", ""),
                "diagnoses": list(site.get("diagnoses") or []),
                # Asked of the signature line itself rather than by comparing dates
                # here. SITE-A carries a practitioner whose licence lapsed in
                # February, and a page that lists them as though they could sign
                # would contradict the one rule this system enforces hardest.
                "practitioners": [
                    {**p, "can_sign": _can_sign(site, p, today)}
                    for p in (site.get("practitioners") or [])
                ],
                "equipment": list(site.get("equipment") or []),
                # Both lists are rendered against the full vocabulary rather than
                # alone, because "SITE-C runs creatinine" is a fact and "SITE-C runs
                # creatinine and nothing else" is the one that explains a referral.
                "labs": [
                    {
                        "code": code,
                        "label": label,
                        "available": code in labs,
                        "gap": evidence_gap(site, code, max_age=max_age, today=today)
                        if code in labs
                        else None,
                    }
                    for code, label in sorted(catalogue.items())
                ],
                "molecules": [{"molecule": m, "stocked": m in stocked} for m in prescribable],
            }
        )

    sites.sort(key=lambda s: s["site_id"])
    return {
        "pack": f"{rules.pack_id}@{rules.version}",
        "evidence_max_age_days": max_age,
        "investigations": [{"code": c, "label": label} for c, label in sorted(catalogue.items())],
        "molecules": prescribable,
        "sites": sites,
    }
