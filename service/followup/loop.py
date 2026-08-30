"""SPEC-V1 §5.11 — the between-visit loop.

A follow-up interval is not a silence. Between visits the patient state keeps
syncing on structured channels — a reading typed into a fixed numeric field, a
refill collected or not collected, an abbreviated symptom checklist — and this
module decides what, if anything, happens as a result.

**No model touches this path.** Escalation here is the same red-flag predicates
the gate already runs, applied to readings that arrived from home. A model in
this loop would be a model deciding, unsupervised, whether to alarm a clinic
about a patient who is not in front of anyone.

**A patient-reported outlier asks for a repeat before it alerts anyone.** Home
readings carry noise a clinic reading does not: wrong cuff, wrong arm, no rest,
a frightened patient. Firing a red flag on one unconfirmed value would train a
clinic to ignore the channel inside a month, and a channel nobody reads is worse
than no channel — it looks like coverage and provides none. A reading from a
connected device is trusted directly; it is not subject to technique error in
the same way, and treating it as noisy would waste the one channel with good
provenance.

Provenance is the reason this is V1 work even though the patient-facing channel
is V1.5. Retrofitting `source` onto readings that have already been stored is
exactly the mistake SPEC §3 exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from service.rules.predicates import Context, PredicateError, evaluate
from service.state.models import Observation, Source


class Action(str, Enum):
    ACCEPT = "accept"            # stored, nothing more to do
    CONFIRM = "confirm"          # alarming, but unconfirmed: ask for a repeat
    ESCALATE = "escalate"        # confirmed red flag; a clinician is alerted
    REFILL_GAP = "refill_gap"    # medication not collected on schedule


@dataclass(frozen=True)
class LoopEvent:
    action: Action
    reason: str
    rule_id: str | None = None
    instruction: str = ""
    instruction_gloss: str = ""
    citation: str | None = None


@dataclass
class LoopResult:
    events: list[LoopEvent] = field(default_factory=list)
    stored: list[Observation] = field(default_factory=list)

    @property
    def escalated(self) -> bool:
        return any(e.action is Action.ESCALATE for e in self.events)

    @property
    def awaiting_confirmation(self) -> bool:
        return any(e.action is Action.CONFIRM for e in self.events)


def _policy(rules) -> dict[str, Any]:
    return (rules.guideline.get("between_visits") or {})


def _red_flags(state, rules) -> list[dict]:
    """Which of this pathway's red flags fire on the state as it now stands."""
    context = Context(state)
    fired = []
    for rule in rules.guideline.get("red_flags") or []:
        try:
            if evaluate(rule["predicate"], context):
                fired.append(rule)
        except PredicateError:
            # Fail closed, as everywhere: an unreadable rule is treated as
            # having fired rather than silently passing a patient.
            fired.append({**rule, "message": f"{rule.get('message', '')} (rule unreadable)"})
    return fired


def ingest(state, rules, readings: list[Observation], *, now: date | None = None) -> LoopResult:
    """Take readings that arrived between visits and decide what follows.

    The state is updated — that is the point of a longitudinal record — but
    nothing clinical is decided here beyond whether to ask for a repeat or to
    alert a clinician.
    """
    policy = _policy(rules)
    confirm = policy.get("confirm_before_escalating") or {}
    noisy_sources = {str(s) for s in (confirm.get("sources") or [])}
    window = timedelta(hours=float(confirm.get("repeat_within_hours", 24)))
    result = LoopResult()

    before = {id(o) for o in state.observations}

    for reading in readings:
        state.observations.append(reading)
        result.stored.append(reading)

        fired = _red_flags(state, rules)
        if not fired:
            result.events.append(
                LoopEvent(Action.ACCEPT, f"{reading.code} {reading.value:g} recorded.")
            )
            continue

        rule = fired[0]
        needs_confirmation = (
            reading.source.value in noisy_sources
            and not _corroborated(state, rules, reading, window, noisy_sources)
        )

        if needs_confirmation:
            result.events.append(
                LoopEvent(
                    Action.CONFIRM,
                    f"{reading.code} {reading.value:g} would trigger "
                    f"{rule.get('id')} but is a single self-reported reading.",
                    rule_id=rule.get("id"),
                    instruction=confirm.get("instruction_text", ""),
                    instruction_gloss=confirm.get("instruction_gloss", ""),
                    citation=rule.get("citation"),
                )
            )
        else:
            result.events.append(
                LoopEvent(
                    Action.ESCALATE,
                    rule.get("message", "Red flag."),
                    rule_id=rule.get("id"),
                    citation=rule.get("citation"),
                )
            )

    # Anything appended that we did not intend to keep would be a bug; assert
    # the invariant rather than trusting it.
    assert len(state.observations) == len(before) + len(readings)
    return result


def _fires(state, rules, observations: list[Observation]) -> bool:
    """Would a red flag fire on a state holding exactly these observations?"""
    return bool(_red_flags(replace(state, observations=list(observations)), rules))


def _corroborated(state, rules, reading: Observation, window: timedelta,
                  noisy_sources: set[str]) -> bool:
    """Is there independent evidence, or is this one reading the whole case?

    An earlier version counted any recent reading of the same measurement as
    corroboration. That was wrong in the direction that matters: a *normal*
    clinic reading was confirming an alarming home one, when it contradicts it.
    Corroboration has to mean a second reading that would also cross the line
    on its own.

    Two ways that can be true. The record already triggers the rule without this
    reading at all — in which case the home reading is not the news. Or a second
    recent self-reported reading would trigger it alone, which is two
    independent measurements agreeing and is exactly what a repeat is for.
    """
    others = [o for o in state.observations if o is not reading]

    if _fires(state, rules, others):
        return True

    recent = [
        o for o in others
        if o.code == reading.code
        and o.source.value in noisy_sources
        and abs(_days(o.taken_at, reading.taken_at)) <= max(window.days, 1)
    ]
    unrelated = [o for o in others if o.code != reading.code]
    return any(_fires(state, rules, unrelated + [candidate]) for candidate in recent)


def _days(a: date, b: date) -> int:
    return (a - b).days


def refill_check(state, rules, *, last_collected: date | None, now: date) -> LoopEvent | None:
    """Twelve dispensing touchpoints a year against four visits.

    A missed refill is an adherence signal the next visit would otherwise
    discover months later, and it needs no patient to type anything.
    """
    refill = (_policy(rules).get("refill") or {})
    if not refill or last_collected is None:
        return None
    due = int(refill.get("expected_every_days", 30)) + int(refill.get("grace_days", 0))
    overdue = (now - last_collected).days - due
    if overdue <= 0:
        return None
    return LoopEvent(
        Action.REFILL_GAP,
        f"{refill.get('message', 'Medication not collected on schedule.')} "
        f"Last collected {(now - last_collected).days} days ago.",
        rule_id="refill_gap",
    )
