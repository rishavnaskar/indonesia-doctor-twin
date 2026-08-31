# Decisions log

Engineering decisions I took while building, with the reasoning you'd need to
overturn them. Clinical decisions aren't in here. Those belong to the clinical
lead and live in the packs with their own review status.

---

### D1: The `Proposal` schema lives in `/service/contracts`, not `/service/reason`

**Why.** The gate has to read a `Proposal`, and the rule is that `/service/gate`
never imports from `/service/reason`. I didn't want to bend that for "it's only
a dataclass", so the shared vocabulary sits in a neutral module that both sides
depend on and neither owns.

**Overturned if:** probably never, while the gate rule stands. The alternative
is an import path from the gate to the reasoning layer, which is the path a
model would eventually travel along.

---

### D2: `Source.EMR`, not the vendor's name

**Why.** BUILD.md §4 forbids naming a country, payer, drug or guideline under
`/service`. The v6 review extended that to the hospital system. The first
adapter targets one specific open-source product, but the moment the service
layer knows that, we've built a product for that vendor rather than a platform.
Adapters do the mapping and the service layer stays ignorant.

**Overturned if:** the group standardises on a single system permanently *and*
we abandon the platform thesis. Both would have to be true.

---

### D3: The predicate evaluator fails closed

**Why.** An unrecognised key, a bad operator, a malformed rule: all of them
raise, and none evaluate to `False`. A red-flag rule that silently becomes "no
red flag" because of a YAML typo produces no output, no error and no alert, so
it's invisible in testing precisely because it produces nothing. The gate engine
catches the exception and turns it into a *block*, so a broken pack closes the
gate instead of opening it.

**Overturned if:** never, I think. This is close to the whole point of having a
gate.

---

### D4: `latest()` resolves same-day ties to the most recently recorded value

**Why.** Found by a failing test. The original used `max()`, which resolves ties
by list position, so it could return the *first* reading of the day rather than
the confirmatory one. Repeat same-day readings are routine here: the measurement
standard asks for a mean of at least two, and a nurse re-checking a high
pressure after five minutes' rest produces exactly this shape. Acting on the
wrong one of a same-day pair is a real clinical error.

**Open:** the guideline asks for a *mean* of two or more readings, which is a
different rule again. Implementing that properly is a clinical-lead question,
not an engineering one.

---

### D5: Sets A and B cannot validate anything clinical, and the code says so

**Why.** The reference proposer follows the same guideline the gate checks
against, so it passes by construction. That proves the pipeline runs and the
contracts hold; it proves nothing about medicine. The scorecard prints this
caveat on every run, so no number gets lifted out of it without the warning
attached.

**Overturned if:** never. Set C (real retrospective visits, blind-scored by
Indonesian physicians) is the only evidence that would really count.

---

### D6: A missing site capability record blocks, rather than assuming availability

**Why.** "We don't know what this site stocks" isn't the same as "this site
stocks everything", and an unknown shouldn't be presented as an executable plan.
The registry can also go stale (assumption A13, unverified), so `as_of` is
mandatory and gets shown on the panel.

---

### D7: The orchestration library is confined to `/service/graph`

**Why.** LangGraph still feels like the right choice *if* one is needed:
interrupt and resume are the signature line, checkpointers are the offline
story, and replay is the audit story. None is imported today, and the rule is
written as a permission rather than a description for that reason. What sits
behind the four-verb interface (`run`/`interrupt`/`resume`/`replay`) is three
plain implementations, in memory, on files and on Postgres, run against one
conformance suite. So the claim that swapping engines is one module's work is
already demonstrated across three backends rather than argued from one. Enforced
in CI rather than by convention.

---

### D8: Prompt injection is answered structurally, not by prompt engineering

**Why.** Untrusted text gets quarantined in `PatientState.intake_notes`, and no
gate check reads that field. Injected instructions can influence what the model
*proposes*, but they can't reach the rules that decide whether the proposal
renders at all. There's a test asserting a hostile intake produces findings
identical to a clean one.

---

### D9: Provenance is built after the model answers, not before

**Why.** It used to get assembled before the call, which recorded what we
intended to ask rather than what actually answered. That's wrong whenever the
backend falls through to a different model, or an alias resolves to a snapshot,
which are the cases where an audit trail matters most. The pin is
`model@served_by`, because the same weights on two serving stacks can differ in
quantisation and sampling defaults.

**Overturned if:** a provider guarantees the served model matches the requested
one and exposes that guarantee. I don't know of one that does.

---

### D10: A pathway is chosen before eligibility, and the engine only ever sees one

**Why.** "Is this the right pathway" comes before "is this patient suitable for
it". Selection swaps a single field, `rules.guideline`, and twelve modules carry
on unmodified, which is the same trick that makes the country swappable applied
one level down. Order between pathways is a clinical judgement about which
problem leads, so it lives in the pack.

**Overturned if:** two pathways have to run on one encounter. That's combined
cardiometabolic management, which is explicitly V3 and probably needs a
different design from picking a winner.

---

### D11: A target is `{code: threshold}`, not two blood pressures

**Why.** `ResolvedTarget` was `sbp_lt` and `dbp_lt`. That shape survived about as
long as there was one pathway. A target that's a single HbA1c made it obvious
the engine had one disease's measurement baked into its idea of a target.
Thresholds now get read from any `<code>_lt` key, so a pathway declares what it
measures.

**Overturned if:** a pathway needs a target that isn't "below a number", e.g. a
range or a trend. Then this becomes a predicate rather than a threshold, and
gate check 2 changes with it.

---

### D12: Refusal routing reads check numbers, never rule ids

**Why.** It used to match `R<digit>` to detect a red flag. A second pack numbered
its red flags `D1..D4`, so hypoglycaemia got correctly caught by check 1 and
then reported as a quiet abstention instead of alerting anyone. The engine had
learned one pack's naming convention and was treating it as a rule. Check
numbers are engine vocabulary and stay stable across packs.

**Overturned if:** probably never, since a rule id is just whatever the pack
author typed.

---

### D13: Reconciliation surfaces discrepancies and resolves none

**Why.** Both sources are routinely wrong, in different ways. A record goes stale
the moment a patient buys something at a pharmacy, and patients misremember
doses. A system that picks a winner is mostly guessing about what someone is
currently swallowing. So neither side gets edited and the clinician gets a
line.

**Overturned if:** a source becomes authoritative enough to overwrite the other.
Dispensing data might one day be, for the drugs it covers.

---

### D14: Self-consistency takes the minimum of stated and observed, and stays off by default

**Why.** Neither signal should rescue the other. Samples agreeing on an answer
the model itself calls uncertain doesn't make it certain, and a model asserting
0.95 while its samples scatter isn't worth believing either. It's off by default
because the evidence for it (two runs, 58 drafts, every error in the unstable
group, p = 0.0043) was measured against labels our own rule engine produced. So
it shows instability predicts divergence from us, which isn't the same claim as
predicting clinical error, and it triples the API calls.

**Overturned if:** Set C shows the same split. Then it becomes a default.

---

### D15: The critic may only lower confidence

**Why.** A second model can catch things rules can't, e.g. a rationale that
doesn't follow, or a plan that ignores the history. It returns a score and the
proposal keeps the minimum. A critic that could *raise* confidence would hold a
veto over the abstention floor, which is probably the one authority nothing here
should have. When it fails, the draft continues and gets marked unreviewed,
partly because an advisory component being down isn't a reason to deny care, and
partly because treating the two as equivalent would make the safeguard
unfalsifiable.

**Overturned if:** never, while the gate is the thing that decides.

---

### D16: Shadow mode exists because the experiment could not answer its own question

**Why.** The first measurement said self-consistency cost abstentions and bought
nothing. But it had been measured through the mechanism being evaluated:
agreement feeds confidence, low agreement falls below the abstention floor,
check 8 deletes it, and the comparison is left with no unstable drafts to
attribute errors to. Shadow mode records agreement without applying it.

**Overturned if:** never. Any future "does this lever help" question probably
needs the same treatment.

---

### D17: A self-reported outlier asks for a repeat before it alerts anyone

**Why.** Home readings carry noise a clinic reading generally doesn't: wrong
cuff, wrong arm, no rest, a frightened patient, etc. Firing a red flag on one
unconfirmed value would probably train a clinic to ignore the channel within a
month, and a channel nobody reads is worse than no channel, because it still
looks like coverage. A device reading gets trusted immediately. Corroboration
means a second reading that would cross the line *on its own*. An earlier
version accepted any recent reading of the same measurement, so a normal clinic
value was confirming an alarming home one when it actually contradicts it.

**Overturned if:** the clinic asks for every reading to alert. That's their call
to make, and it's a pack value rather than a code change.

---

### D18: `is_synthetic` is never inferred, and defaults to False

**Why.** It decides whether a record can cross the residency boundary. A record
typed into a form or pasted as JSON isn't synthetic just because it arrived
through a form. Real-until-proven-otherwise seems like the only safe direction
for this particular flag, and the interactive surface shows the refusal rather
than smoothing it away.

**Overturned if:** never.

---

### D19: A `fullUrl` is derived from the resource id, never generated

**Why.** Every write gets replayed after a connectivity gap. A random UUID would
differ between attempts, so one encounter submitted twice would arrive as two
encounters, which is the duplicate the offline queue exists to prevent. `uuid5`
over a fixed namespace makes the same resource always yield the same urn.

**Overturned if:** never, while replay exists. Randomness and idempotency pull
in opposite directions here.

---

### D20: A blood pressure is one Observation with two components

**Why.** It was two Observations, one per reading, which reads naturally enough
but isn't a legal FHIR blood pressure. A systolic or diastolic LOINC code
triggers the blood-pressure profile, which wants the panel code, both readings
as components, and a vital-signs category. Six of the official validator's nine
errors came out of that one modelling choice.

**Overturned if:** the profile changes. That's the spec's call rather than
ours.

---

### D21: A code's `display` is omitted rather than guessed

**Why.** We were writing our own label into it: a role description in the ICD-10
display, and a short name for a LOINC code whose registered name runs to a line
and a half. The validator rejects a display that isn't the code's registered
name, and I think it's right to, because a wrong display is worse than no
display when a reader believes it. FHIR lets you omit it.

**Overturned if:** we hold the authoritative display names, which means shipping
the terminology, which is a real project rather than a field.

---

### D22: English leads, and which language leads is one flag

**Why.** Both strings are always carried and no rule reads either, so this is
display and nothing else. It defaults to English because the people reading this
build are reviewing it, not practising from it. `Labels.english_first=False`
flips it, and a deployed clinic would set that, since a doctor shouldn't have to
read past a second language to reach the sentence that matters.

**Overturned if:** the surface gets deployed for real. Then the default is wrong,
and the flag is why changing it costs nothing.

---

### D23: A reading dated after the encounter was not available at it

**Why.** Age is `as_of - taken_at`, so a future-dated observation produces a
negative age and satisfies *every* freshness rule in the pack. "Potassium within
90 days" would pass on a lab that doesn't exist yet. One clock skew or mistyped
year and the sufficiency check quietly stops asking for the test it exists to
demand. Excluded at the source rather than patched at the six comparison sites,
because `as_of` already means "what the system saw".

**Overturned if:** never.

---

### D24: A proposal naming one drug twice is rejected, not reconciled

**Why.** The resulting regimen is keyed by molecule, so a second entry overwrote
the first and the discarded one never got dose-checked. Seen live: "increase
metformin 1000 mg x3" sitting beside "continue metformin 1000 mg x2", i.e. 3000
mg against a 2000 ceiling, which vanished, and the survivor passed. Working out
which instruction the model meant is the kind of guess this system tries not to
make about a medication list, and a splittable dose is a way around check 3 for
anything that learns to split it.

**Overturned if:** never.

---

### D25: Conformance is checked against the validator, not against our reading of the spec

**Why.** There's a hand-written conformance test and it's worth having, since it
runs in CI, needs no download, and catches regressions. It isn't a substitute
though. The official validator found nine errors it had missed, and one of those
was a bug the hand-written test had introduced itself (a `fullUrl` fix that
broke bundle reference resolution). Approximating a specification generally
isn't the same as checking against it.

**Overturned if:** never. Worth keeping both: the approximation on every commit,
and the real one before anything gets submitted.

---

### D26: The audit log's append-only rule is enforced by the database, not by the application

**Why.** Three JSONL files already survived a power cut, which is most of what
durability means here, so the case for a database had to be better than "real
systems use one". It's this: append-only was a convention, and a convention
isn't really a control. Any text editor can rewrite a signature in a JSONL file,
and nothing in the file records that it happened. The signature is the artefact
that makes an output lawful, so that matters. The migration installs a trigger
that raises on `UPDATE` and `DELETE` for all three tables, so the rule holds
against this application, against a later migration script, and against somebody
sitting at a `psql` prompt.

It raises rather than discarding the write. Postgres will happily let a rule
swallow an `UPDATE` instead, and that's arguably worse than no protection, since
an ignored `UPDATE` looks identical to a successful one from the caller's side,
on a table whose whole job is being trustworthy.

Two smaller reasons that wouldn't have justified it alone: two clinicians at one
site are two processes appending to one file, and "which encounters are still
unsent" becomes one statement instead of a scan of everything ever written.

**Overturned if:** never, while a signature is the thing that makes an output
lawful. If the store moves to something without triggers, the equivalent control
(revoked `UPDATE`/`DELETE` grants, or an immutable log service) has to arrive in
the same change rather than after it.

---

### D27: Postgres is preferred and optional, and the system says which one it chose

**Why.** Roughly one facility in twelve doesn't have power around the clock and
one in five has unreliable connectivity. A clinical system that won't start
without a database is one that often doesn't start, and the sites where it would
fail tend to be the remote ones the programme exists to serve. So `Store`
prefers Postgres, falls back to files, and reports `backend` on every summary
and in the clinician surface's own header.

The reporting half matters as much as the fallback. Degrading silently turns
"did that signature persist" into a question nobody thinks to ask, and then the
record is missing at the moment somebody finally asks for it.

Both backends satisfy the same three interfaces and
`tests/test_runtime_contract.py` runs the *same* tests against all three
implementations rather than a suite per backend. A durable backend that quietly
differs in semantics is arguably worse than none, because what runs in a clinic
then behaves unlike what ran in the test.

**Overturned if:** a deployment can guarantee a database, and dropping the file
backend buys something real. Worth noting that removing it means deleting a
tested implementation rather than dead code.

---

### D28: Migrations are numbered SQL, applied by both the container and the application

**Why.** Postgres runs `/docker-entrypoint-initdb.d` once, on an empty data
directory. That covers a fresh `docker compose up` and not much else: an
existing database gets no migrations that way, and neither does a deployment
pointed at a Postgres somebody else operates. So the same directory also gets
applied at startup against a `schema_migrations` tracking table.

The consequence is that the first application start after a fresh container
always re-applies files the container has already run, since the tables exist
but the tracking table is empty. Rather than making the two paths exclusive and
having to reason about which one ran, every statement in a migration is written
to be safe to run twice, and the two paths are allowed to converge. There's a
test that re-running against an existing schema doesn't raise.

**Overturned if:** a real migration can't be made idempotent, e.g. a destructive
column rewrite. At that point the tracking table becomes authoritative and the
initdb mount goes away, which is a one-line change to `docker-compose.yml`.

---

### D29: An encounter's thread id is derived from its inputs, so a second run replays instead of re-running

**Why.** Two problems with one answer. The durable runtime was writing
checkpoints that nothing ever read back, so the checkpoint wasn't really doing
any work. And every reload of the clinician surface re-ran nine encounters, i.e.
nine model calls on a rate-limited free tier each time somebody opened the page,
which made the second demo of the day slower than the first for no good
reason.

The thread id is now a hash of everything that could change the answer: the
scenario, the patient state, the site, the pack and its version, the drafter,
and whether the scenario tampers with the router. A run that finds a stored
result for the same id replays it. The scripted page costs nine model calls once
and zero after that, and says how many it replayed rather than leaving you to
infer it from the page loading faster. (`make live` has a second model-calling
stage, which D33 covers. The whole run is 14 calls once, then none.)

Invalidation is most of the risk, so it's derived rather than remembered.
Editing a guideline file moves a digest of the pack's contents, which moves
every id, which keeps the "edit a pack, refresh, watch the verdict move"
property the surface exists to demonstrate. The digest rather than the declared
`version` string, because that string is written by hand: I edited five pack
files without touching it, and every stored encounter would have replayed
against the old text. `RuleSet.content_digest` hashes the pack directory, the
ids key on it, and a test asserts an edit moves it while the version stays put.
The version is still what gets displayed as provenance, since a human reads
`id-2026-08-29` and a human cannot read a hash. `CLINICIAN_FRESH=1` forces a re-run, because watching a
live model disagree with itself across runs is a reasonable thing to want, and
it's what resumption otherwise hides.

Two keys were wrong before this one was right, and both failed quietly:
`backend.version()` rewrites itself to `model@served_by` after a hosted
backend's first reply, so nothing ever resumed; and returning `"reference"`
whenever the router could not name a backend collided with how the reference
reasoner names *itself*, so a router that failed every draft replayed the
reference reasoner's successes and the page reported zero failures. The router's
class is part of the key now, since failing to name a backend isn't itself a
name.

**Overturned if:** the surface stops being the demo artefact, or somebody finds
an input that can change an answer which the id doesn't cover. The second one is
the live risk. Anything added to the encounter path that affects the result has
to be added to `_thread_id`, or it'll get silently cached across the change.

---

### D30: `default_dir()` and the backend flag are read per call, never at import

**Why.** Both started as module-level constants reading the environment once, at
import. That's invisible until something sets the variable after the import,
which in a test suite is basically everything. Each test pointed the store at
its own temporary directory, every one of them silently shared a single
directory instead, and a test asserting a fresh store found the previous test's
encounters sitting in it.

It showed up as a resumption test failing only when run with the rest of the
suite and passing on its own, which is usually the shape this bug takes.

**Overturned if:** never. Configuration read at import can't be overridden by
anything that runs later, which includes every test and every embedding
process.

---

### D31: Clearing the clinic list writes a marker forward; it never deletes

**Why.** `/clinic` restores every visit run in an earlier session, which is what
makes it a prototype rather than a demo. It also means the list grows, and a
list that only grows needs a way to be cleared.

The obvious implementation is a `DELETE`, and the store refuses one, which is
D26 working as designed. So clearing writes a `cleared` marker with a timestamp
and the page lists only what came after it. The visits stay on the record and
stay replayable through `python -m tools.store`.

I think this is worth more than the trigger it works around. Anyone can add a
constraint. The more interesting question is what happens the first time the
product wants to violate it, and here the feature changed shape while the
constraint stayed put.

**Overturned if:** a real retention policy arrives, at which point deletion
becomes a supervised operation with its own audit record rather than a button on
a page.

---

### D32: `/clinic` runs sequentially unless a model was named

**Why.** The concurrency decision read `router is None` fifteen lines after
`router = router or default_router()` had made that permanently false, so every
interactive run went three-wide, including reference-reasoner runs where
concurrency buys nothing and costs the deterministic ordering the restored list
is sorted by. The check now reads whether the *caller* named a drafter, captured
before the default gets applied.

Found by a test asserting restored visits come back newest-first, which failed
intermittently on the ordering rather than on the thing it was written to check.

**Overturned if:** never. A decision that reads a variable the code has already
overwritten is a bug whatever it happens to decide.

---

### D33: Both model-calling stages resume, and a replay says so on every line

**Why.** `make live` has two stages that call a model: the live runner and the
clinician surface. Only the surface resumed, so the claim "the second run makes
no model calls" was off by five calls, and it had gone into the README that way
before anyone checked. The live runner is now content-addressed on the same
basis (patient, pack and version, site, the configured model, and the sampling
options), because a draft agreed by three samples and checked by a critic isn't
the same draft one call produced.

The label matters as much as the resumption. That stage exists to show a real
model is behind the router, so a replayed encounter that reads like a fresh one
is a demo claiming an API call it didn't make. Every replayed line carries
`[replayed from the store, no model call]`, and the run closes with how many
were replayed against how many calls were made.

Failures store nothing. A response that didn't parse, or a request that got
rate-limited, isn't an answer, and storing it would replay the failure forever
without ever retrying the call that might succeed. Seen on the first run of the
pair that verified this: one encounter failed to parse, wasn't stored, and
correctly called the model again on the second run while the other two
replayed.

**Overturned if:** a third thing starts calling a model without going through
one of these two paths. Then the key probably belongs in one place rather than
implemented twice, which is where it is now, mostly because the two stages key
on different inputs and a shared abstraction would have to take both.

---

### D34: `--reset` is a person's command, and it is the only thing that lifts the triggers

**Why.** A prototype's store fills up with synthetic demo runs, and starting a
recording from a clean slate is a real need. But the append-only triggers refuse
`DELETE`, which is D26 working, so something has to suspend them and the
question is what that something is allowed to be.

It's a command a person types. Not a flag on `make`, not a startup path, and not
anything a run can reach on its own. It prints what it's about to destroy, names
the backend, and waits for the word `yes`, because "start afresh before a
recording" and "delete the signatures a licensed doctor put their name to" are
the same keystroke here, and only one of them is ever what somebody meant.

It's explicitly not what `/clinic`'s *Clear this list* does. That writes a marker
forward and destroys nothing, which is the behaviour the product has. This one
is the operator's version, and in a real deployment I don't think it would ship
at all, since destroying a clinical audit trail is unlawful rather than just
inadvisable.

There's a test that it puts the triggers back. A reset that left them off would
turn the store's central guarantee into one that held until the first time
somebody started clean, and it would hide, because an append-only table behaves
much like a mutable one right up until someone mutates it. The test inserts rows
before checking, because a row-level trigger on an empty table fires zero times
and an `UPDATE` against one succeeds whether the trigger is there or not. That's
how the first version of the check fooled itself.

**Overturned if:** this ever runs anywhere real, at which point deletion becomes
a supervised operation with its own audit record and this command goes away.
