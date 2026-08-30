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

from dataclasses import dataclass, field, replace
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

    `text` is the deployment language where the pack supplies one and the
    engine's English otherwise; `gloss` is the English, for a reviewer who does
    not read the deployment language. An untranslated finding shows an empty
    gloss and its English in `text` — a visible gap rather than a silent
    fallback nobody notices for a year.

    `rule_id` and `citation` travel with the text rather than being looked up
    later. A clinician who cannot see why the system said something has no way
    to disagree with it, and a system a clinician cannot disagree with is one
    they will eventually stop reading.
    """

    # `text` leads and `gloss` sits beneath it. Which language fills which is
    # Labels.english_first — a display choice, not a change to what is stored.
    text: str
    gloss: str = ""
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
    """Display text, read from the pack. Never written in this file.

    `english_first` decides which of the two languages leads. It is a display
    choice and nothing else: both strings are always carried, the pack is
    unchanged, and no rule reads either of them.

    It defaults to English because the people reading this build are reviewing
    it, not practising from it. **A deployed clinic flips it** — a doctor in the
    deployment country should not have to read past a second language to reach
    the sentence that matters, and the same rule that keeps a drug name out of
    the engine says the local text is the real text. One flag, no pack change.
    """

    bands: dict[str, str] = field(default_factory=dict)
    headlines: dict[str, str] = field(default_factory=dict)
    english_first: bool = True
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

    def primary(self, key: str) -> str:
        """What leads."""
        if self.english_first:
            return self.glosses.get(key) or self.headline(key)
        return self.headline(key)

    def secondary(self, key: str) -> str:
        """What sits beneath it, when the two differ."""
        first, other = (
            (self.glosses.get(key), self.headlines.get(key))
            if self.english_first
            else (self.headlines.get(key), self.glosses.get(key))
        )
        return other or "" if first else ""

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


def _lines(findings: list[Finding], english_first: bool = True) -> tuple[Line, ...]:
    def pair(finding: Finding) -> tuple[str, str]:
        if english_first:
            return finding.message, finding.message_local
        return (finding.message_local or finding.message,
                finding.message if finding.message_local else "")

    lines = []
    for finding in findings:
        text, gloss = pair(finding)
        lines.append(Line(text=text, gloss=gloss, rule_id=finding.rule_id,
                          citation=finding.citation, check=finding.check))
    return tuple(lines)


_BAND_ORDER = {Band.GREEN: 0, Band.AMBER: 1, Band.RED: 2}


def _raise_for_concerns(view: "Presentation", concerns: tuple, labels: Labels) -> "Presentation":
    """Let the drafter add to what the clinician sees. Never subtract.

    The deterministic red flags decide the floor. A concern can push the band
    up — mention to amber, escalate to red — and cannot push it down, cannot
    clear an acknowledgement the rules demanded, and cannot turn a refusal into
    a draft. That asymmetry is the whole reason a model is allowed to speak
    here: the worst a wrong concern costs is a clinician's attention.
    """
    if not concerns:
        return view

    wanted = Band.RED if any(
        getattr(c, "urgency", None) and c.urgency.value == "escalate" for c in concerns
    ) else Band.AMBER
    band = view.band if _BAND_ORDER[view.band] >= _BAND_ORDER[wanted] else wanted

    lines = view.lines + tuple(
        Line(text=c.text, citation=getattr(c, "citation", None)) for c in concerns
    )
    return replace(
        view,
        band=band,
        # A green visit that gains a concern needs a headline, since silence is
        # exactly what the concern is objecting to.
        headline=view.headline if view.band is not Band.GREEN else labels.primary("warnings"),
        gloss=view.gloss if view.band is not Band.GREEN else labels.secondary("warnings"),
        lines=lines,
        requires_acknowledgement=view.requires_acknowledgement or band is Band.RED,
        audit=view.audit + tuple(Line(text=c.text) for c in concerns),
    )


def present(
    outcome: str,
    labels: Labels,
    *,
    decision: GateDecision | None = None,
    questions: tuple[str, ...] = (),
    discrepancies: tuple = (),
    concerns: tuple = (),
) -> Presentation:
    """Decide what the clinician sees. Pure, and deterministic.

    Takes the outcome and the gate's findings rather than the workflow result,
    so this module never imports the orchestration layer — presentation depends
    on what was concluded, not on what ran it.
    """
    concerns = tuple(concerns)
    findings = list(decision.findings) if decision else []
    blocking = [f for f in findings if f.severity is Severity.BLOCK]
    warnings = [f for f in findings if f.severity is Severity.WARN]
    audit = _lines(findings, labels.english_first)

    # A material reconciliation discrepancy is not a gate finding — nothing is
    # wrong with the draft. It is a disagreement about what the patient is
    # actually taking, and it is amber for the same reason a warning is: the
    # clinician can act on it, and nobody else in the room can.
    def _discrepancy_line(d) -> Line:
        suffix = f" Interacts with {', '.join(d.interacts_with)}." if d.interacts_with else ""
        lead, under = (d.gloss or d.text, d.text if d.gloss else "") if labels.english_first \
            else (d.text, d.gloss)
        return Line(text=lead + suffix, gloss=under)

    material = tuple(
        _discrepancy_line(d) for d in discrepancies if getattr(d, "material", False)
    )
    audit = audit + tuple(Line(text=d.gloss or d.text, gloss=d.text if d.gloss else "")
                          for d in discrepancies)

    # A red flag is not a suggestion and is not suppressible. It is the one
    # case where the system interrupts a clinician who has not asked.
    if outcome == _ESCALATE:
        return _raise_for_concerns(Presentation(
            band=Band.RED,
            headline=labels.primary(_ESCALATE),
            gloss=labels.secondary(_ESCALATE),
            lines=_lines(blocking, labels.english_first) or audit,
            requires_acknowledgement=True,
            shows_draft=False,
            audit=audit,
        ), concerns, labels)

    # A plan that cannot be delivered at this site is not a bad plan. It is a
    # referral, and the clinician has to see it, because the alternative is a
    # patient sent home waiting for a test that will never be run here.
    if decision is not None and decision.referral:
        return _raise_for_concerns(Presentation(
            band=Band.RED,
            headline=labels.primary("referral"),
            gloss=labels.secondary("referral"),
            lines=_lines([f for f in blocking if f.converts_to_referral], labels.english_first),
            requires_acknowledgement=True,
            shows_draft=False,
            audit=audit,
        ), concerns, labels)

    if outcome == _HANDOFF:
        return _raise_for_concerns(Presentation(
            band=Band.AMBER,
            headline=labels.primary(_HANDOFF),
            gloss=labels.secondary(_HANDOFF),
            lines=_lines(blocking, labels.english_first),
            shows_draft=False,
            audit=audit,
        ), concerns, labels)

    if outcome == _REQUEST_INFO:
        return _raise_for_concerns(Presentation(
            band=Band.AMBER,
            headline=labels.primary(_REQUEST_INFO),
            gloss=labels.secondary(_REQUEST_INFO),
            lines=tuple(Line(text=q) for q in questions) or _lines(blocking, labels.english_first),
            shows_draft=False,
            audit=audit,
        ), concerns, labels)

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
        return _raise_for_concerns(Presentation(
            band=Band.GREEN,
            headline=labels.primary(_ABSTAIN),
            gloss=labels.secondary(_ABSTAIN),
            lines=(),
            shows_draft=False,
            audit=audit,
        ), concerns, labels)

    if warnings or material:
        return _raise_for_concerns(Presentation(
            band=Band.AMBER,
            headline=labels.primary("warnings"),
            gloss=labels.secondary("warnings"),
            lines=_lines(warnings, labels.english_first) + material,
            shows_draft=True,
            audit=audit,
        ), concerns, labels)

    return _raise_for_concerns(Presentation(
        band=Band.GREEN,
        headline=labels.primary("clean"),
            gloss=labels.secondary("clean"),
        lines=(),
        shows_draft=True,
        audit=audit,
    ), concerns, labels)
