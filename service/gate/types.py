"""Gate vocabulary.

/service/gate imports nothing from /service/reason's logic, never imports the
orchestration library, and — checked by a test that inspects sys.modules — never
pulls YAML into its import graph. It must be testable with nothing else running,
readable by a doctor, and diffable in git.

Type-only imports below are deliberately inside TYPE_CHECKING so the runtime
import graph stays clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - types only, never imported at runtime
    from service.packs.loader import RuleSet
    from service.contracts.proposal import Proposal
    from service.state.models import PatientState


class Severity(str, Enum):
    NONE = "none"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class Finding:
    check: int  # 1..9
    check_name: str
    severity: Severity
    message: str
    rule_id: str | None = None
    citation: str | None = None
    # Gate check 9: a plan that cannot be delivered here is not a bad plan,
    # it is a referral. The distinction changes what the clinician is shown.
    converts_to_referral: bool = False


@dataclass
class GateContext:
    state: "PatientState"
    proposal: "Proposal"
    rules: "RuleSet"
    site: dict[str, Any] | None = None


@dataclass
class GateDecision:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARN]

    @property
    def rendered(self) -> bool:
        """Whether the clinician sees the proposal at all.

        On any blocking failure the proposal does not render: the clinician sees
        the encounter as if the assistant had said nothing, plus a quiet log
        entry. Failing silently toward 'no output' is the correct direction.
        """
        return not self.blocking

    @property
    def abstained(self) -> bool:
        return bool(self.blocking)

    @property
    def referral(self) -> bool:
        return any(f.converts_to_referral for f in self.blocking)

    def reasons(self) -> list[str]:
        return [f"[{f.check}:{f.rule_id or f.check_name}] {f.message}" for f in self.blocking]
