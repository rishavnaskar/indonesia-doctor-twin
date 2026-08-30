"""Run the official HL7 validator over the bundles this system emits.

    make fhir                       # after downloading the validator once
    python -m tools.validate_fhir --jar path/to/validator_cli.jar

The validator is a ~190 MB Java distribution, so it is not vendored and not a
dependency. Point `FHIR_VALIDATOR_JAR` at it, or pass --jar.

Why bother when there is already a conformance test: because the hand-written
one missed things the real validator caught, and one of the things it caught was
a bug the hand-written one had *introduced*. Approximating a specification is
not the same as checking against it.

    Download once:
      curl -L -o validator_cli.jar \\
        https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from datagen.synthetic import make_diabetic, make_patient
from service.emit.coding import build_claim
from service.emit.fhir import build_bundle
from service.packs.loader import load_pack
from service.reason import reference
from service.rules import pathways

RESULT = re.compile(r"(?:Success|\*FAILURE\*): (\d+) errors?, (\d+) warnings?")


def sample_bundles(rules) -> dict[str, dict]:
    """One bundle per pathway per control state, at different sites."""
    cases = [
        ("htn-uncontrolled", "hypertension", make_patient(101, controlled=False), "SITE-A"),
        ("htn-controlled", "hypertension", make_patient(102, controlled=True), "SITE-B"),
        ("dm-uncontrolled", "diabetes", make_diabetic(201, controlled=False), "SITE-A"),
        ("dm-controlled", "diabetes", make_diabetic(202, controlled=True), "SITE-C"),
    ]
    out = {}
    for name, pathway, state, site_id in cases:
        view = pathways.with_pathway(rules, pathway)
        site = view.sites[site_id]
        out[name] = build_bundle(
            state, build_claim(state, view), reference.propose(state, view, site),
            site, site["practitioners"][0]["practitioner_id"], view,
            encounter_id=f"ENC-{name}",
        ).payload
    return out


def validate(jar: Path, payload: dict, name: str) -> tuple[int, int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        proc = subprocess.run(
            ["java", "-jar", str(jar), str(path), "-version", "4.0.1"],
            capture_output=True, text=True, timeout=900,
        )
    output = proc.stdout + proc.stderr
    match = RESULT.search(output)
    if not match:
        return -1, -1, output[-800:]
    return int(match.group(1)), int(match.group(2)), output


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate emitted bundles against HL7 R4.")
    parser.add_argument("--jar", default=os.environ.get("FHIR_VALIDATOR_JAR"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.jar or not Path(args.jar).exists():
        print("\n  The HL7 validator was not found.")
        print("  Set FHIR_VALIDATOR_JAR, or pass --jar, after downloading it once:\n")
        print("    curl -L -o validator_cli.jar \\")
        print("      https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/"
              "download/validator_cli.jar\n")
        print("  It is ~190 MB, which is why it is neither vendored nor a dependency.\n")
        return 2

    rules = load_pack("id")
    print("\n  Official HL7 FHIR R4 validator")
    print("  " + "=" * 58)
    failed = 0
    for name, payload in sample_bundles(rules).items():
        errors, warnings, output = validate(Path(args.jar), payload, name)
        if errors < 0:
            print(f"  {name:<20} could not parse the validator's output")
            failed += 1
            continue
        mark = "PASS" if errors == 0 else "FAIL"
        print(f"  [{mark}] {name:<20} {errors} errors, {warnings} warnings")
        failed += 1 if errors else 0
        if args.verbose or errors:
            for line in output.splitlines():
                if "Error @" in line:
                    print(f"        {line.split('Error @ ')[-1][:140]}")
    print("  " + "=" * 58)
    print("  Remaining warnings are best-practice recommendations — narrative text\n"
          "  and UCUM annotations — not conformance failures.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
