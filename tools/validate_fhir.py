"""Run the official HL7 validator over the bundles this system emits.

    python -m tools.validate_fhir --download    # once: ~190 MB into .tools/
    python -m tools.validate_fhir               # run it (also runs inside `make`)
    python -m tools.validate_fhir --jar path/to/validator_cli.jar

The validator is a ~190 MB Java distribution, so it is not vendored and not a
dependency. Point `FHIR_VALIDATOR_JAR` at it, or pass --jar.

Why bother when there is already a conformance test: because the hand-written
one missed things the real validator caught, and one of the things it caught was
a bug the hand-written one had *introduced*. Approximating a specification is
not the same as checking against it.

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

# Gitignored: 190 MB does not belong in a repository, and it is the same file
# for everyone.
DEFAULT_JAR = Path(__file__).resolve().parents[1] / ".tools" / "validator_cli.jar"
JAR_URL = ("https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/"
           "download/validator_cli.jar")


def download(destination: Path = DEFAULT_JAR) -> int:
    """Fetch the validator. Separate command because it is 190 MB.

    Deliberately not done automatically by the run: a build that silently pulls
    a fifth of a gigabyte the first time somebody types `make` is a build that
    has decided something on their behalf.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n  Downloading the HL7 FHIR validator (~190 MB) to {destination} ...")
    result = subprocess.run(
        ["curl", "-L", "--progress-bar", "-o", str(destination), JAR_URL]
    )
    if result.returncode != 0:
        print("  Download failed. It is a plain file — fetch it by hand from:")
        print(f"      {JAR_URL}\n")
        return 1
    print("  Done. It will be used automatically from now on.\n")
    return 0


def _find_jar(explicit: str | None) -> Path | None:
    """--jar, then FHIR_VALIDATOR_JAR, then where --download puts it."""
    for candidate in (explicit, os.environ.get("FHIR_VALIDATOR_JAR"), DEFAULT_JAR):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


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
    parser.add_argument("--jar", default=None)
    parser.add_argument("--download", action="store_true",
                        help="fetch the validator once (~190 MB, gitignored)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.download:
        return download()

    jar = _find_jar(args.jar)
    if jar is None:
        # Not a failure. A missing optional tool is a missing prerequisite, and
        # exiting non-zero here made the runner print "Error 2" underneath the
        # instructions — which reads as something broken rather than something
        # not yet downloaded.
        print("\n  The HL7 validator is not here yet. One command, once:\n")
        print("      python -m tools.validate_fhir --download\n")
        print(f"  It downloads ~190 MB to {DEFAULT_JAR.parent}/ (gitignored), which is")
        print("  why it is neither vendored nor a dependency. FHIR_VALIDATOR_JAR")
        print("  overrides the location if you already have one.\n")
        return 0
    args.jar = str(jar)

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
