"""Check 3 — drug safety.

Dose ceilings, allergy, and class-level interactions evaluated against the
regimen the patient would end up on. There is no Indonesian equivalent of a
commercial pharmacology database, so these rules are hand-curated per pathway
and live in the pack. Ten molecules is small enough for a pharmacist to verify
by hand — which is the whole reason V1 is one pathway.
"""

from __future__ import annotations

from service.gate.regimen import classes_in, resulting_regimen
from service.gate.types import Finding, GateContext, Severity

NUMBER = 3
NAME = "drug_safety"


def run(ctx: GateContext) -> list[Finding]:
    findings: list[Finding] = []
    rules, state, proposal = ctx.rules, ctx.state, ctx.proposal
    regimen = resulting_regimen(state, proposal)
    by_class = classes_in(regimen, rules)

    # ---- dose ceilings, on changed drugs only -----------------------------
    for drug in regimen.values():
        if not drug.changed:
            continue
        mol = rules.molecules.get(drug.molecule)
        if mol is None:
            continue  # membership is check 5's job

        dosing = mol.dosing
        if drug.mg_per_dose is None or drug.doses_per_day is None:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=f"{drug.molecule}: a dose change with no dose stated.",
                    rule_id="dose_incomplete",
                )
            )
            continue

        max_per_dose = dosing.get("max_mg_per_dose")
        if max_per_dose is not None and drug.mg_per_dose > max_per_dose:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{drug.molecule}: {drug.mg_per_dose:g} mg per dose exceeds the "
                        f"maximum of {max_per_dose:g} mg."
                    ),
                    rule_id="dose_per_dose",
                    citation=mol.citation,
                )
            )

        max_doses = dosing.get("max_doses_daily")
        if max_doses is not None and drug.doses_per_day > max_doses:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{drug.molecule}: {drug.doses_per_day} doses a day exceeds the "
                        f"maximum of {max_doses:g}."
                    ),
                    rule_id="dose_frequency",
                    citation=mol.citation,
                )
            )

        max_daily = dosing.get("max_mg_daily")
        if max_daily is not None and drug.mg_daily is not None and drug.mg_daily > max_daily:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=(
                        f"{drug.molecule}: {drug.mg_daily:g} mg daily exceeds the maximum "
                        f"of {max_daily:g} mg."
                    ),
                    rule_id="dose_daily",
                    citation=mol.citation,
                )
            )

        min_daily = dosing.get("min_mg_daily")
        if min_daily is not None and drug.mg_daily is not None and drug.mg_daily < min_daily:
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.WARN,
                    message=(
                        f"{drug.molecule}: {drug.mg_daily:g} mg daily is below the usual "
                        f"minimum of {min_daily:g} mg."
                    ),
                    rule_id="dose_subtherapeutic",
                    citation=mol.citation,
                )
            )

    # ---- allergy ----------------------------------------------------------
    allergens = {a.substance.lower() for a in state.allergies}
    for drug in regimen.values():
        cls = rules.drug_class_of(drug.molecule)
        if drug.molecule.lower() in allergens or (cls and cls.lower() in allergens):
            findings.append(
                Finding(
                    check=NUMBER,
                    check_name=NAME,
                    severity=Severity.BLOCK,
                    message=f"{drug.molecule} appears on this patient's allergy list.",
                    rule_id="allergy",
                )
            )

    # ---- interactions, from the pack --------------------------------------
    for rule in rules.interactions:
        rtype = rule.get("type")
        severity = Severity.BLOCK if rule.get("severity") == "block" else Severity.WARN

        if rtype == "class_combination":
            classes = rule.get("classes", [])
            if all(by_class.get(c) for c in classes):
                molecules = sorted(m for c in classes for m in by_class.get(c, []))
                findings.append(
                    Finding(
                        check=NUMBER,
                        check_name=NAME,
                        severity=severity,
                        message=f"{rule['message'].strip()} Present: {', '.join(molecules)}.",
                        rule_id=rule.get("id"),
                        citation=rule.get("citation"),
                    )
                )

        elif rtype == "requires_recent_labs":
            applies = set(rule.get("applies_to_classes", []))
            touched = [
                d.molecule
                for d in regimen.values()
                if d.changed and rules.drug_class_of(d.molecule) in applies
            ]
            if not touched:
                continue
            within = int(rule.get("within_days", 90))
            missing = []
            for code in rule.get("codes", []):
                age = state.observation_age_days(code)
                if age is None:
                    missing.append(f"{code} (absent)")
                elif age > within:
                    missing.append(f"{code} ({age} days old)")
            if missing:
                findings.append(
                    Finding(
                        check=NUMBER,
                        check_name=NAME,
                        severity=severity,
                        message=(
                            f"{rule['message'].strip()} Missing or stale: "
                            f"{', '.join(missing)}. Affects {', '.join(sorted(touched))}."
                        ),
                        rule_id=rule.get("id"),
                        citation=rule.get("citation"),
                    )
                )

    return findings
