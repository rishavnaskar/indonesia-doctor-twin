"""SPEC-V1 §5.8 PRESENT — the clinician surface, deterministic.

Three bands, and the discipline is in the first one.

  green  — silent. The clinician sees nothing at all.
  amber  — collapsed, optional, one line.
  red    — must be acknowledged before the order can be committed.

**Green being silent is the load-bearing decision.** Most visits are green, and
the silence is the only reason amber and red are worth reading. A surface that
says "no issues found" on every routine visit has spent the clinician's
attention before the one visit that matters, and alert fatigue is the
best-documented way for a system like this to fail — it fails by being ignored
at exactly the wrong moment, and the log will show it fired correctly.

Nothing here decides anything. Every band is a function of what the gate and the
router already concluded; this module chooses how loudly to say it. That is why
it is deterministic and why it lives outside /service/reason.

No country, drug, payer or guideline is named here, and no display text is
written here either. Labels arrive from the pack's language component, because
/service is not allowed to name a language any more than it is allowed to name a
drug. Swapping the pack swaps what the clinician reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from service.gate.types import Finding, GateDecision, Severity


class Band(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


@dataclass(frozen=True)
class Line:
    """One thing the clinician can read, with its provenance attached.

    `rule_id` and `citation` travel with the text rather than being looked up
    later. A clinician who cannot see why the system said something has no way
    to disagree with it, and a system a clinician cannot disagree with is one
    they will eventually stop reading.
    """

    text: str
    rule_id: str | None = None
    citation: str | None = None
    check: int | None = None


@dataclass(frozen=True)
class Presentation:
    band: Band
    headline: str
    gloss: str = ""
    lines: tuple[Line, ...] = ()
    requires_acknowledgement: bool = False
    shows_draft: bool = False

    # Always populated, including on green, and never shown to the clinician in
    # the normal surface. This is what the system checked and concluded when it
    # decided to stay quiet. A supervisor, an auditor and a regulator each need
    # it; the clinician mid-consultation does not.
    audit: tuple[Line, ...] = ()

    @property
    def silent(self) -> bool:
        """Green shows the clinician nothing. Not a summary, not a tick."""
        return self.band is Band.GREEN


@dataclass(frozen=True)
class Labels:
    """Display text, read from the pack. Never written in this file."""

    bands: dict[str, str] = field(default_factory=dict)
    headlines: dict[str, str] = field(default_factory=dict)
    # English glosses of the headlines. For reviewers and auditors who do not
    # read the deployment language — never shown to the clinician, who does.
    glosses: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_pack(cls, language: dict[str, Any]) -> "Labels":
        block = (language or {}).get("presentation") or {}
        return cls(
            bands={k: str(v) for k, v in (block.get("bands") or {}).items()},
            headlines={k: str(v) for k, v in (block.get("headlines") or {}).items()},
            glosses={k: str(v) for k, v in (block.get("glosses") or {}).items()},
        )

    def gloss(self, key: str) -> str:
        return self.glosses.get(key, "")

    def headline(self, key: str) -> str:
        # A missing label is a pack defect, and it surfaces as a visible marker
        # rather than an empty string or a silently invented English sentence.
        return self.headlines.get(key) or f"<missing label: {key}>"

    def band(self, band: Band) -> str:
        return self.bands.get(band.value) or f"<missing label: {band.value}>"


# Outcomes that are safe conclusions rather than failures, mapped to the band
# each one earns. The keys are the workflow's own outcome values; they are
# generic process words, not clinical or national vocabulary.
_ESCALATE = "escalate"
_HANDOFF = "handoff"
_REQUEST_INFO = "request_info"
_ABSTAIN = "abstain"


def _lines(findings: list[Finding]) -> tuple[Line, ...]:
    return tuple(
        Line(text=f.message, rule_id=f.rule_id, citation=f.citation, check=f.check)
        for f in findings
    )


def present(
    outcome: str,
    labels: Labels,
    *,
    decision: GateDecision | None = None,
    questions: tuple[str, ...] = (),
    discrepancies: tuple = (),
) -> Presentation:
    """Decide what the clinician sees. Pure, and deterministic.

    Takes the outcome and the gate's findings rather than the workflow result,
    so this module never imports the orchestration layer — presentation depends
    on what was concluded, not on what ran it.
    """
    findings = list(decision.findings) if decision else []
    blocking = [f for f in findings if f.severity is Severity.BLOCK]
    warnings = [f for f in findings if f.severity is Severity.WARN]
    audit = _lines(findings)

    # A material reconciliation discrepancy is not a gate finding — nothing is
    # wrong with the draft. It is a disagreement about what the patient is
    # actually taking, and it is amber for the same reason a warning is: the
    # clinician can act on it, and nobody else in the room can.
    material = tuple(
        Line(text=d.text + (
            f" Interacts with {', '.join(d.interacts_with)}." if d.interacts_with else ""
        ))
        for d in discrepancies if getattr(d, "material", False)
    )
    audit = audit + tuple(Line(text=d.text) for d in discrepancies)

    # A red flag is not a suggestion and is not suppressible. It is the one
    # case where the system interrupts a clinician who has not asked.
    if outcome == _ESCALATE:
        return Presentation(
            band=Band.RED,
            headline=labels.headline(_ESCALATE),
            gloss=labels.gloss(_ESCALATE),
            lines=_lines(blocking) or audit,
            requires_acknowledgement=True,
            shows_draft=False,
            audit=audit,
        )

    # A plan that cannot be delivered at this site is not a bad plan. It is a
    # referral, and the clinician has to see it, because the alternative is a
    # patient sent home waiting for a test that will never be run here.
    if decision is not None and decision.referral:
        return Presentation(
            band=Band.RED,
            headline=labels.headline("referral"),
            gloss=labels.gloss("referral"),
            lines=_lines([f for f in blocking if f.converts_to_referral]),
            requires_acknowledgement=True,
            shows_draft=False,
            audit=audit,
        )

    if outcome == _HANDOFF:
        return Presentation(
            band=Band.AMBER,
            headline=labels.headline(_HANDOFF),
            gloss=labels.gloss(_HANDOFF),
            lines=_lines(blocking),
            shows_draft=False,
            audit=audit,
        )

    if outcome == _REQUEST_INFO:
        return Presentation(
            band=Band.AMBER,
            headline=labels.headline(_REQUEST_INFO),
            gloss=labels.gloss(_REQUEST_INFO),
            lines=tuple(Line(text=q) for q in questions) or _lines(blocking),
            shows_draft=False,
            audit=audit,
        )

    if outcome == _ABSTAIN or blocking:
        # The gate refused and there is nothing here the clinician must act on.
        # The draft does not render and the clinician is not interrupted: they
        # continue exactly as they would without the system. The reasons are
        # logged, and they are in `audit`, which the consultation surface does
        # not show.
        #
        # This is the direction to fail in. A system that cannot produce a safe
        # draft has nothing useful to say, and saying it anyway trains people to
        # skim.
        return Presentation(
            band=Band.GREEN,
            headline=labels.headline(_ABSTAIN),
            gloss=labels.gloss(_ABSTAIN),
            lines=(),
            shows_draft=False,
            audit=audit,
        )

    if warnings or material:
        return Presentation(
            band=Band.AMBER,
            headline=labels.headline("warnings"),
            gloss=labels.gloss("warnings"),
            lines=_lines(warnings) + material,
            shows_draft=True,
            audit=audit,
        )

    return Presentation(
        band=Band.GREEN,
        headline=labels.headline("clean"),
            gloss=labels.gloss("clean"),
        lines=(),
        shows_draft=True,
        audit=audit,
    )
