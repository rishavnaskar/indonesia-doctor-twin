# Decisions log

Engineering decisions taken while building, with the reasoning that would be
needed to overturn them. Clinical decisions are not here — they belong to the
clinical lead and live in the packs with their own review status.

---

### D1 — The `Proposal` schema lives in `/service/contracts`, not `/service/reason`

**Why.** The gate has to read a `Proposal`, and the rule is that `/service/gate`
never imports from `/service/reason`. Rather than bend that rule for "it's only
a dataclass", the shared vocabulary sits in a neutral module that both sides
depend on and neither owns.

**Overturned if:** never, while the gate rule stands. The alternative is an
import path from the gate to the reasoning layer, which is exactly the path a
model eventually travels along.

---

### D2 — `Source.EMR`, not the vendor's name

**Why.** BUILD.md §4 forbids naming a country, payer, drug or guideline under
`/service`. The v6 review extended that to the hospital system: the first
adapter targets one specific open-source product, but the moment the service
layer knows that, we have built a product for that vendor. Adapters map; the
service layer stays ignorant.

**Overturned if:** the group standardises on a single system permanently *and*
we abandon the platform thesis. Both would have to be true.

---

### D3 — The predicate evaluator fails closed

**Why.** An unrecognised key, a bad operator, a malformed rule: all raise. None
evaluate to `False`. A red-flag rule that silently becomes "no red flag" because
of a YAML typo produces no output, no error and no alert — invisible in testing
precisely because it produces nothing. The gate engine catches the exception and
converts it to a *block*, so a broken pack closes the gate rather than opening
it.

**Overturned if:** never. This is the property the gate exists for.

---

### D4 — `latest()` resolves same-day ties to the most recently recorded value

**Why.** Found by a failing test. The original used `max()`, which resolves ties
by list position and could therefore return the *first* reading of the day
rather than the confirmatory one. Repeat same-day readings are routine here —
the measurement standard asks for a mean of at least two, and a nurse
re-checking a high pressure after five minutes' rest produces exactly this
shape. Acting on the wrong one of a same-day pair is a real clinical error.

**Open:** the guideline asks for a *mean* of two or more readings, which is a
different rule again. Implementing that properly is a clinical-lead question,
not an engineering one.

---

### D5 — Sets A and B cannot validate anything clinical, and the code says so

**Why.** The reference proposer follows the same guideline the gate checks
against, so it passes by construction. That proves the pipeline runs and the
contracts hold; it proves nothing about medicine. The scorecard prints this
caveat on every run so no number can be lifted out of it without the warning
attached.

**Overturned if:** never. Set C — real retrospective visits, blind-scored by
Indonesian physicians — is the only evidence that counts.

---

### D6 — A missing site capability record blocks, rather than assuming availability

**Why.** "We don't know what this site stocks" is not "this site stocks
everything". An unknown must not be presented as an executable plan. The
registry can also go stale (assumption A13, unverified), so `as_of` is mandatory
and surfaced.

---

### D7 — The orchestration library is confined to `/service/graph`

**Why.** LangGraph remains the right choice as a library — interrupt/resume is
the signature line, checkpointers are the offline story, replay is the audit
story. But the dependency is confined behind a four-verb interface
(`run`/`interrupt`/`resume`/`replay`) so that swapping engines is one module's
work. Enforced in CI, not by convention.

---

### D8 — Prompt injection is answered structurally, not by prompt engineering

**Why.** Untrusted text is quarantined in `PatientState.intake_notes` and no
gate check reads it. Injected instructions can influence what the model
*proposes*; they cannot reach the rules that decide whether the proposal
renders. There is a test asserting that a hostile intake produces findings
identical to a clean one.
