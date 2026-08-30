"""Pack loading.

The only module in the codebase that reads YAML. Everything downstream —
critically the gate — receives plain Python objects, so it stays stdlib-only and
testable with nothing else running.

A pack is data and rules, not code. Swapping the pack swaps the country.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PACKS_ROOT = Path(__file__).resolve().parents[2] / "packs"


class PackError(RuntimeError):
    pass


@dataclass(frozen=True)
class Molecule:
    molecule: str
    drug_class: str
    forms_mg: list[float]
    dosing: dict[str, float]
    restrictions: list[dict[str, Any]]
    citation: str
    confidence: str
    note: str | None = None


@dataclass
class RuleSet:
    pack_id: str
    version: str
    review_status: str

    molecules: dict[str, Molecule] = field(default_factory=dict)
    # Molecules we never prescribe but must recognise on a patient's list.
    # Prescribable is a strict subset of recognised — check 5 tests membership
    # of `molecules`, never of this.
    recognised: dict[str, str] = field(default_factory=dict)  # molecule -> class
    interactions: list[dict[str, Any]] = field(default_factory=list)
    guideline: dict[str, Any] = field(default_factory=dict)
    sites: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Closed vocabulary for the proposal's `investigations` field. Gate check 9
    # tests membership of a site's list; this is the set of codes that are
    # meaningful to test at all, so an unrecognised value can be named as a
    # malformed proposal rather than misreported as unavailable here.
    investigations: dict[str, str] = field(default_factory=dict)
    payer: dict[str, Any] = field(default_factory=dict)
    interop: dict[str, Any] = field(default_factory=dict)
    language: dict[str, Any] = field(default_factory=dict)
    # Display text only: what each code and term means in plain words. No rule
    # reads this, and none should — a wrong value here misleads a reader without
    # changing a decision.
    glossary: dict[str, Any] = field(default_factory=dict)

    # Every citation string any rule may legitimately point at. Gate check 6
    # tests membership against exactly this set: no source, no answer.
    citations: set[str] = field(default_factory=set)

    def molecules_in_class(self, drug_class: str) -> set[str]:
        return {m.molecule for m in self.molecules.values() if m.drug_class == drug_class}

    def drug_class_of(self, molecule: str) -> str | None:
        m = self.molecules.get(molecule)
        if m:
            return m.drug_class
        return self.recognised.get(molecule)

    def is_prescribable(self, molecule: str) -> bool:
        return molecule in self.molecules


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PackError(f"pack component missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise PackError(f"pack component is not a mapping: {path}")
    return data


def _collect_citations(node: Any, into: set[str]) -> None:
    """Walk any loaded structure and harvest every `citation` value."""
    if isinstance(node, dict):
        cite = node.get("citation")
        if isinstance(cite, str):
            into.add(cite)
        for value in node.values():
            _collect_citations(value, into)
    elif isinstance(node, list):
        for item in node:
            _collect_citations(item, into)


def load_pack(pack_id: str = "id", root: Path | None = None) -> RuleSet:
    base = (root or PACKS_ROOT) / pack_id
    manifest = _read(base / "pack.yaml")
    components = manifest.get("components") or {}

    formulary = _read(base / components["formulary"])
    interactions = _read(base / components["interactions"])
    guideline = _read(base / components["guideline"])
    capability = _read(base / components["capability"])
    payer = _read(base / components["payer"])
    interop = _read(base / components["interop"]) if "interop" in components else {}
    language = _read(base / components["language"]) if "language" in components else {}
    glossary = _read(base / components["glossary"]) if "glossary" in components else {}

    molecules: dict[str, Molecule] = {}
    for row in formulary.get("molecules", []):
        try:
            mol = Molecule(
                molecule=row["molecule"],
                drug_class=row["drug_class"],
                forms_mg=[float(f) for f in row.get("forms_mg", [])],
                dosing=dict(row.get("dosing") or {}),
                restrictions=list(row.get("restrictions") or []),
                citation=row["citation"],
                confidence=row.get("confidence", "unverified"),
                note=row.get("note"),
            )
        except KeyError as exc:  # a malformed formulary row is fatal, never skipped
            raise PackError(f"formulary row missing {exc} in {row!r}") from exc
        molecules[mol.molecule] = mol

    recognised: dict[str, str] = {}
    for row in formulary.get("recognised_molecules", []) or []:
        try:
            recognised[row["molecule"]] = row["drug_class"]
        except KeyError as exc:
            raise PackError(f"recognised_molecules row missing {exc} in {row!r}") from exc

    citations: set[str] = set()
    for blob in (formulary, interactions, guideline):
        _collect_citations(blob, citations)

    rs = RuleSet(
        pack_id=manifest["pack_id"],
        version=manifest["version"],
        review_status=(manifest.get("review") or {}).get("status", "unknown"),
        molecules=molecules,
        recognised=recognised,
        interactions=list(interactions.get("rules") or []),
        guideline=guideline,
        sites={s["site_id"]: s for s in capability.get("sites", [])},
        investigations={
            row["code"]: row.get("label", row["code"])
            for row in (capability.get("investigation_catalogue") or [])
        },
        payer=payer,
        interop=interop,
        language=language,
        glossary=glossary,
        citations=citations,
    )
    _validate(rs)
    return rs


def _validate(rs: RuleSet) -> None:
    """Cheap structural checks. A broken pack should fail at load, not at a bedside."""
    if not rs.molecules:
        raise PackError("formulary is empty")
    if not rs.guideline.get("red_flags"):
        raise PackError("guideline defines no red flags")
    if not rs.guideline.get("targets"):
        raise PackError("guideline defines no targets")
    if not rs.investigations:
        raise PackError("capability defines no investigation_catalogue")

    # A site offering a lab that is not in the catalogue means the two halves of
    # the pack disagree, and check 9 would silently never match it.
    for site_id, site in rs.sites.items():
        unknown = set(site.get("labs_available") or []) - set(rs.investigations)
        if unknown:
            raise PackError(
                f"{site_id} offers investigations absent from the catalogue: {sorted(unknown)}"
            )

    known_classes = {m.drug_class for m in rs.molecules.values()} | set(rs.recognised.values())
    for rule in rs.interactions:
        for cls in list(rule.get("classes", [])) + list(rule.get("applies_to_classes", [])):
            if cls not in known_classes:
                raise PackError(f"interaction {rule.get('id')} references unknown class {cls!r}")

    for mol in rs.molecules.values():
        for restriction in mol.restrictions:
            rtype = restriction.get("type")
            if rtype not in (
                "requires_documented_intolerance",
                "requires_diagnosis",
                "requires_recent_labs",
            ):
                raise PackError(f"{mol.molecule}: unknown restriction type {rtype!r}")


def is_signed_off(rs: RuleSet) -> bool:
    """SPEC-V1 §2 clinical governance gate.

    No rule set is clinically active until the clinical lead has signed it off
    against the primary source. Callers running against real patients must
    refuse when this is False. Synthetic evaluation is allowed either way.
    """
    return rs.review_status == "signed_off"
