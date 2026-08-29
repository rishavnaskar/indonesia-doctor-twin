"""The signature line, enforced in software.

"A licensed doctor signs everything" is the load-bearing constraint of this
whole system, and a constraint that lives only in a policy document is a
constraint nobody has implemented. This module is where it becomes code.

A signature is refused unless the practitioner is on the site's roster and
their practising licence is current *at the moment of signing*. An expired
licence is refused exactly like an unsigned prescription, because legally it is
one.

The audit record binds four things together, and all four are required: who
signed, what exactly they signed (the proposal with its three provenance pins),
what they decided, and when. Any one missing makes the record unusable later —
which is to say, makes it useless precisely when someone asks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


class SignatureRefused(PermissionError):
    """Raised rather than returned. A refused signature must not be ignorable."""


@dataclass(frozen=True)
class Signer:
    practitioner_id: str
    authenticated: bool


@dataclass(frozen=True)
class SignatureRecord:
    practitioner_id: str
    role: str
    licence_expires: date
    decision: str  # accepted | edited | rejected
    proposal_provenance: tuple[str, str, str]
    signed_at: datetime
    rejection_reason: str | None = None
    edit_diff: str | None = None


@dataclass
class AuditLog:
    records: list[SignatureRecord] = field(default_factory=list)

    def append(self, record: SignatureRecord) -> None:
        self.records.append(record)


def verify_signer(site: dict[str, Any], signer: Signer, when: date) -> dict[str, Any]:
    if not signer.authenticated:
        raise SignatureRefused("Signer is not authenticated.")

    roster = {p["practitioner_id"]: p for p in (site.get("practitioners") or [])}
    practitioner = roster.get(signer.practitioner_id)
    if practitioner is None:
        raise SignatureRefused(
            f"{signer.practitioner_id} is not on the roster for "
            f"{site.get('site_id', 'this site')}."
        )

    expires = practitioner.get("sip_expires")
    if not expires:
        raise SignatureRefused(f"{signer.practitioner_id} has no recorded licence expiry.")
    expiry = date.fromisoformat(expires) if isinstance(expires, str) else expires
    if expiry < when:
        raise SignatureRefused(
            f"{signer.practitioner_id}'s practising licence expired on {expiry.isoformat()}."
        )

    return practitioner


def sign(
    site: dict[str, Any],
    signer: Signer,
    proposal: Any,
    decision: str,
    when: datetime,
    audit: AuditLog,
    *,
    rejection_reason: str | None = None,
    edit_diff: str | None = None,
) -> SignatureRecord:
    """Bind a decision to a person and a proposal, or refuse."""
    if decision not in ("accepted", "edited", "rejected"):
        raise ValueError(f"unknown decision {decision!r}")

    practitioner = verify_signer(site, signer, when.date())

    provenance = proposal.provenance
    if provenance is None or not provenance.complete():
        raise SignatureRefused(
            "Refusing to bind a signature to an unpinned proposal: it could not "
            "be reconstructed later."
        )

    record = SignatureRecord(
        practitioner_id=signer.practitioner_id,
        role=practitioner["role"],
        licence_expires=date.fromisoformat(practitioner["sip_expires"]),
        decision=decision,
        proposal_provenance=(provenance.model, provenance.prompt_template, provenance.corpus),
        signed_at=when,
        rejection_reason=rejection_reason,
        edit_diff=edit_diff,
    )
    audit.append(record)
    return record
