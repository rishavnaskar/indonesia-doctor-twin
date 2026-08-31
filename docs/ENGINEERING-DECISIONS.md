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

---

### D9 — Provenance is built after the model answers, not before

**Why.** It used to be assembled before the call, which recorded what we
intended to ask rather than what answered. That is wrong whenever the backend
falls through to a different model or an alias resolves to a snapshot — exactly
the cases where an audit trail matters. The pin is `model@served_by`, because
the same weights on two serving stacks can differ in quantisation and sampling
defaults.

**Overturned if:** a provider guarantees the served model matches the requested
one and exposes that guarantee. Nobody does.

---

### D10 — A pathway is chosen before eligibility, and the engine only ever sees one

**Why.** "Is this the right pathway" comes before "is this patient suitable for
it". Selection swaps a single field, `rules.guideline`, and twelve modules carry
on unmodified — which is the same trick that makes the country swappable,
applied one level down. Order between pathways is a clinical judgement about
which problem leads, so it lives in the pack.

**Overturned if:** two pathways must run on one encounter. That is combined
cardiometabolic management, explicitly V3, and it needs a different design than
picking a winner.

---

### D11 — A target is `{code: threshold}`, not two blood pressures

**Why.** `ResolvedTarget` was `sbp_lt` and `dbp_lt`. That shape survived exactly
as long as there was one pathway; a target that is a single HbA1c made it
obvious the engine had one disease's measurement baked into its idea of a
target. Thresholds are read from any `<code>_lt` key, so a pathway declares what
it measures.

**Overturned if:** a pathway needs a target that is not "below a number" — a
range, or a trend. Then this becomes a predicate rather than a threshold, and
gate check 2 changes with it.

---

### D12 — Refusal routing reads check numbers, never rule ids

**Why.** It used to match `R<digit>` to detect a red flag. A second pack
numbered its red flags `D1..D4`, so hypoglycaemia was correctly caught by check
1 and then reported as a quiet abstention instead of alerting anyone. The engine
had learned a pack's naming convention and called it a rule. Check numbers are
engine vocabulary and stable across packs.

**Overturned if:** never. A rule id is whatever the pack author typed.

---

### D13 — Reconciliation surfaces discrepancies and resolves none

**Why.** Both sources are routinely wrong in different ways — a record goes
stale the moment a patient buys something at a pharmacy, and a patient
misremembers a dose. A system that picks a winner is guessing about what someone
is currently swallowing. Neither side is edited; the clinician gets a line.

**Overturned if:** a source becomes authoritative enough to overwrite the other.
Dispensing data might one day be, for the drugs it covers.

---

### D14 — Self-consistency takes the minimum of stated and observed, and stays off by default

**Why.** Neither signal may rescue the other: samples agreeing on an answer the
model calls uncertain does not make it certain, and a model asserting 0.95 while
its samples scatter is not to be believed. Off by default because the evidence
for it — two runs, 58 drafts, every error in the unstable group, p = 0.0043 —
was measured against labels our own rule engine produced. It shows instability
predicts divergence from us, which is not the same claim as predicting clinical
error, and it triples the API calls.

**Overturned if:** Set C shows the same split. Then it becomes a default.

---

### D15 — The critic may only lower confidence

**Why.** A second model catches what rules cannot — a rationale that does not
follow, a plan that ignores the history. It returns a score and the proposal
keeps the minimum. A critic that could *raise* confidence would hold a veto over
the abstention floor, which is the one authority nothing here may have. When it
fails the draft continues and is marked unreviewed, because an advisory
component being down is not a reason to deny care, and because treating the two
as equivalent would make the safeguard unfalsifiable.

**Overturned if:** never, while the gate is the thing that decides.

---

### D16 — Shadow mode exists because the experiment could not answer its own question

**Why.** The first measurement said self-consistency cost abstentions and bought
nothing. It had been measured through the mechanism being evaluated: agreement
feeds confidence, low agreement falls below the abstention floor, check 8
deletes it, and the comparison is left with no unstable drafts to attribute
errors to. Shadow mode records agreement without applying it.

**Overturned if:** never. Any future "does this lever help" question needs the
same treatment, and this is the shape of it.

---

### D17 — A self-reported outlier asks for a repeat before it alerts anyone

**Why.** Home readings carry noise a clinic reading does not — wrong cuff, wrong
arm, no rest, a frightened patient. Firing a red flag on one unconfirmed value
would train a clinic to ignore the channel within a month, and a channel nobody
reads is worse than none because it looks like coverage. A device reading is
trusted immediately. Corroboration means a second reading that would cross the
line *on its own*: an earlier version accepted any recent reading of the same
measurement, so a normal clinic value was confirming an alarming home one when
it contradicts it.

**Overturned if:** the clinic asks for every reading to alert. That is their call
to make, and it is a pack value, not a code change.

---

### D18 — `is_synthetic` is never inferred, and defaults to False

**Why.** It decides whether a record may cross the residency boundary. A record
typed into a form or pasted as JSON is not synthetic because it arrived through
a form. Real-until-proven-otherwise is the only safe direction for this
particular flag, and the interactive surface shows the refusal rather than
smoothing it away.

**Overturned if:** never.

---

### D19 — A `fullUrl` is derived from the resource id, never generated

**Why.** Every write is replayed after a connectivity gap. A random UUID would
differ between attempts, so one encounter submitted twice would arrive as two
encounters — the exact duplicate the offline queue exists to prevent. `uuid5`
over a fixed namespace makes the same resource always yield the same urn.

**Overturned if:** never, while replay exists. Randomness and idempotency are
the same decision pointing in opposite directions.

---

### D20 — A blood pressure is one Observation with two components

**Why.** It was two Observations, one per reading, which reads naturally and is
not a legal FHIR blood pressure: a systolic or diastolic LOINC code triggers the
blood-pressure profile, which requires the panel code, both readings as
components, and a vital-signs category. Six of the official validator's nine
errors came from that one modelling choice.

**Overturned if:** the profile changes. It is the spec's decision, not ours.

---

### D21 — A code's `display` is omitted rather than guessed

**Why.** We were writing our own label into it — a role description in the
ICD-10 display, and a short name for a LOINC code whose registered name runs to
a line and a half. The validator rejects a display that is not the code's
registered name, and it is right to: a wrong display is worse than none, because
a reader believes it. FHIR permits omitting it.

**Overturned if:** we hold the authoritative display names, which means shipping
the terminology, which is a real project rather than a field.

---

### D22 — English leads, and which language leads is one flag

**Why.** Both strings are always carried and no rule reads either, so this is
display and nothing else. It defaults to English because the people reading this
build are reviewing it, not practising from it. `Labels.english_first=False`
flips it, and a deployed clinic sets that — a doctor should not read past a
second language to reach the sentence that matters.

**Overturned if:** the surface is deployed. Then the default is wrong and the
flag is why that costs nothing.

---

### D23 — A reading dated after the encounter was not available at it

**Why.** Age is `as_of - taken_at`, so a future-dated observation produces a
negative age and satisfies *every* freshness rule in the pack — "potassium
within 90 days" would pass on a lab that does not exist yet. One clock skew or
mistyped year and the sufficiency check silently stops asking for the test it
exists to demand. Excluded at the source rather than patched at the six
comparison sites, because `as_of` already means "what the system saw".

**Overturned if:** never.

---

### D24 — A proposal naming one drug twice is rejected, not reconciled

**Why.** The resulting regimen is keyed by molecule, so a second entry
overwrote the first and the discarded one was never dose-checked. Observed
live: "increase metformin 1000 mg x3" beside "continue metformin 1000 mg x2" —
3000 mg against a 2000 ceiling, vanished, survivor passed. Choosing which
instruction the model meant is the guess this system refuses to make about a
medication list, and a splittable dose is a route around check 3 for anything
that learns to split it.

**Overturned if:** never.

---

### D25 — Conformance is checked against the validator, not against our reading of the spec

**Why.** There is a hand-written conformance test and it is worth having: it
runs in CI, needs no download, and catches regressions. It is not a substitute.
The official validator found nine errors it had missed, and one of those was a
bug the hand-written test had itself introduced — a `fullUrl` fix that broke
bundle reference resolution. Approximating a specification is not the same as
checking against it.

**Overturned if:** never. Keep both: the approximation for every commit, the
real one before anything is submitted.

---

### D26 — The audit log's append-only rule is enforced by the database, not by the application

**Why.** Three JSONL files already survived a power cut, which is most of what
durability means here, so the case for a database had to be more than "real
systems use one". It is this: append-only was a convention, and a convention is
not a control. Any text editor rewrites a signature in a JSONL file and nothing
in the file records that it happened — and the signature is the artefact that
makes an output lawful. The migration installs a trigger that raises on `UPDATE`
and `DELETE` for all three tables, so the rule holds against this application,
against a later migration script, and against somebody at a `psql` prompt.

It raises rather than discarding the write. Postgres will happily let a rule
swallow an `UPDATE` instead, and that is worse than no protection: an ignored
`UPDATE` is indistinguishable from a successful one to the caller, on a table
whose entire job is being trustworthy.

Two smaller reasons that would not have justified it alone: two clinicians at
one site are two processes appending to one file, and "which encounters are
still unsent" is one statement rather than a scan of everything ever written.

**Overturned if:** never, while a signature is the thing that makes an output
lawful. If the store moves to something without triggers, the equivalent
control — revoked `UPDATE`/`DELETE` grants, an immutable log service — has to
arrive in the same change, not after it.

---

### D27 — Postgres is preferred and optional, and the system says which one it chose

**Why.** About one facility in twelve lacks 24-hour power and one in five has
unreliable connectivity. A clinical system that will not start without a
database is a clinical system that does not start, and the sites where it would
fail are exactly the remote ones the programme exists to serve. So `Store`
prefers Postgres, falls back to files, and reports `backend` on every summary
and in the clinician surface's own header.

The reporting is the load-bearing half. A silent fallback turns "did that
signature persist" into a question nobody thinks to ask, which is the failure
mode where the record is missing precisely when someone asks for it.

Both backends satisfy the same three interfaces and
`tests/test_runtime_contract.py` runs the *same* tests against all three
implementations rather than a suite per backend. A durable backend that quietly
differs in semantics is worse than none, because what runs in a clinic then
behaves unlike what ran in the test.

**Overturned if:** a deployment can guarantee a database, and losing the file
backend is what buys something real. Note that removing it means deleting a
tested implementation, not deleting dead code.

---

### D28 — Migrations are numbered SQL, applied by both the container and the application

**Why.** Postgres runs `/docker-entrypoint-initdb.d` once, on an empty data
directory. That covers a fresh `docker compose up` and nothing else: an existing
database gets no migrations that way, and neither does a deployment pointed at a
Postgres somebody else operates. So the same directory is also applied at
startup against a `schema_migrations` tracking table.

The consequence is that the first application start after a fresh container
always re-applies files the container has already run — the tables exist, the
tracking table is empty. Rather than making the two paths exclusive and having
to reason about which one ran, every statement in a migration is written to be
safe to run twice and the two paths are allowed to converge. There is a test
that re-running against an existing schema does not raise.

**Overturned if:** a real migration cannot be made idempotent — a destructive
column rewrite, say. At that point the tracking table becomes authoritative and
the initdb mount goes away, which is a one-line change to `docker-compose.yml`.

---

### D29 — An encounter's thread id is derived from its inputs, so a second run replays instead of re-running

**Why.** Two problems, one answer. The durable runtime was writing checkpoints
nothing ever read, which makes a checkpoint decoration rather than a
mechanism. And every reload of the clinician surface re-ran nine encounters —
nine model calls on a rate-limited free tier every time somebody reloaded the
page, which made the second demo of the day slower than the first for no reason.

The thread id is now a hash of everything that could change the answer: the
scenario, the patient state, the site, the pack and its version, the drafter,
and whether the scenario tampers with the router. A run that finds a stored
result for the same id replays it. The scripted page costs nine model calls once
and zero thereafter, and states how many it replayed rather than leaving it to
be inferred from the page appearing faster. (`make live` has a second
model-calling stage, which D33 covers — the whole run is 14 calls once, then
none.)

Invalidation is the whole risk, so it is derived rather than remembered: editing
a guideline file moves the pack version, which moves every id, which preserves
the "edit a pack, refresh, watch the verdict move" property that the surface
exists to demonstrate. `CLINICIAN_FRESH=1` forces a re-run, because watching a
live model disagree with itself across runs is a real thing to want and is
precisely what resumption otherwise hides.

Two keys were wrong before this one was right, and both failed quietly:
`backend.version()` rewrites itself to `model@served_by` after a hosted
backend's first reply, so nothing ever resumed; and returning `"reference"`
whenever the router could not name a backend collided with how the reference
reasoner names *itself*, so a router that failed every draft replayed the
reference reasoner's successes and the page reported zero failures. The router's
class is part of the key now — failing to name a backend is not a name.

**Overturned if:** the surface stops being the demo artefact, or an input that
can change an answer is found that the id does not cover. The second is the
live risk: anything added to the encounter path that affects the result must be
added to `_thread_id`, or it will be silently cached across the change.

---

### D30 — `default_dir()` and the backend flag are read per call, never at import

**Why.** Both started as module-level constants reading the environment once,
at import. That is invisible until something sets the variable after the
import — which in the test suite is everything: each test pointed the store at
its own temporary directory, every one of them silently shared a single
directory instead, and a test asserting a fresh store found the previous test's
encounters sitting in it.

It surfaced as a resumption test failing only when run with the rest of the
suite and passing on its own, which is the shape this bug always takes.

**Overturned if:** never. Configuration read at import is configuration that
cannot be overridden by anything that runs later, which includes every test and
every embedding process.

---

### D31 — Clearing the clinic list writes a marker forward; it never deletes

**Why.** `/clinic` restores every visit run in an earlier session, which is what
makes it a prototype rather than a demo. It also means the list grows, and a
list that only grows needs a way to be cleared.

The obvious implementation is a `DELETE`, and the store refuses one — that is
D26 working as designed. So clearing writes a `cleared` marker with a timestamp
and the page lists only what came after it. The visits stay on the record and
stay replayable by `python -m tools.store`.

This is worth more than the trigger it works around. Anyone can add a
constraint; the question a reviewer actually has is what happens the first time
the product wants to violate it. The answer here is that the feature changed
shape and the constraint did not.

**Overturned if:** a real retention policy arrives, at which point deletion
becomes a supervised operation with its own audit record — never a button on a
page.

---

### D32 — `/clinic` runs sequentially unless a model was named

**Why.** The concurrency decision read `router is None` fifteen lines after
`router = router or default_router()` had made that permanently false, so every
interactive run went three-wide — including reference-reasoner runs, where
concurrency buys nothing and costs the deterministic ordering that the restored
list is sorted by. The check now reads whether the *caller* named a drafter,
captured before the default is applied.

Found by a test asserting restored visits come back newest-first, which failed
intermittently on the ordering rather than on anything it was written to check.

**Overturned if:** never. A decision that reads a variable the code has already
overwritten is a bug whatever it decides.

---

### D33 — Both model-calling stages resume, and a replay says so on every line

**Why.** `make live` has two stages that call a model: the live runner and the
clinician surface. Only the surface resumed, so the claim "the second run makes
no model calls" was false by five calls — and it was written in the README that
way before anyone checked. The live runner is now content-addressed on the same
basis: patient, pack and version, site, the configured model, and the sampling
options, because a draft agreed by three samples and checked by a critic is not
the draft one call produced.

The label is the load-bearing part. That stage exists to prove a real model is
behind the router, so a replayed encounter that reads like a fresh one is a demo
claiming an API call it did not make. Every replayed line carries `[replayed
from the store — no model call]`, and the run closes with how many were replayed
against how many calls were actually made.

Failures store nothing. A response that did not parse, or a request that was
rate-limited, is not an answer — storing it would replay the failure forever and
never retry the call that might succeed. Observed on the first run of the pair
that verified this: one encounter failed to parse, was not stored, and correctly
called the model again on the second run while the other two replayed.

**Overturned if:** a third thing starts calling a model without going through
one of these two paths. Then the key belongs in one place rather than
implemented twice, which it is now — deliberately, because the two stages key on
different inputs and a shared abstraction would have to take both.

---

### D34 — `--reset` is a person's command, and it is the only thing that lifts the triggers

**Why.** A prototype's store fills with synthetic demo runs, and starting a
recording from a clean slate is a real need. But the append-only triggers refuse
`DELETE` — that is D26 working — so something has to suspend them, and the
question is what that something is allowed to be.

It is a command a person types. Not a flag on `make`, not a startup path, not
anything a run can reach. It prints what it is about to destroy, names the
backend, and waits for the word `yes`, because "start afresh before a recording"
and "delete the signatures a licensed doctor put their name to" are the same
keystroke here and only one of them is what anybody meant.

It is explicitly not what `/clinic`'s *Clear this list* does. That writes a
marker forward and destroys nothing, which is the behaviour the product has;
this is the operator's hammer, and in a real deployment it would not ship,
because destroying a clinical audit trail is unlawful rather than merely
inadvisable.

There is a test that it puts the triggers back. A reset that left them off would
turn the store's central guarantee into one that held until the first time
somebody started clean — and it would hide, because an append-only table behaves
exactly like a mutable one right up until someone mutates it. The test inserts
rows before checking, because a row-level trigger on an empty table fires zero
times and an `UPDATE` against one succeeds whether the trigger is there or not.
That is how the first version of the check fooled itself.

**Overturned if:** this ever runs anywhere real, at which point deletion becomes
a supervised operation with its own audit record and this command goes away.
