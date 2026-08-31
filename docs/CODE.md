# The prototype

The code that implements [SPEC-V1.md](SPEC-V1.md). Start here if you are
building; start at [README.md](../README.md) if you are deciding.

```bash
make          # everything, offline, then the clinician surface in a browser
make live     # the same, with a real model drafting instead of the reference reasoner
```

That is the whole interface. There used to be fourteen targets, which is
fourteen ways to run a subset and one way to think you ran all of it; `make`
now runs the lot in order and stops at the first thing that fails, so "it
passed" means the same thing every time. What it runs, in order:

| | |
|---|---|
| Architecture rules | no country, payer, drug or guideline named in the engine |
| Test suite | every safety property, across all three storage backends |
| Scorecard | the seven gates that decide whether this is allowed to run |
| Pressure suite | hostile input, in Indonesian, against the deterministic gate |
| FHIR conformance | the official HL7 validator over the emitted bundles |
| Walkthrough | one narrated encounter per outcome |
| *(`make live` only)* | five encounters through a real model |
| Clinician surface | `localhost:8000`; `/clinic` is the interactive one |

The pieces are still individually runnable when you're working on one of them:
`python -m eval.scorecard`, `python -m eval.pressure`, `python -m
tools.concordance`, `python -m tools.store`, `python -m tools.live
--show-prompt`, `python -m tools.live --list-free`, `python -m tools.demo
--export demo.html`, etc. `python -m tools.run --ci` is what CI runs, i.e. the
gates only, with no walkthrough, no browser and no model.

### Running against a real model

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' >> .env    # .env is gitignored
python -m tools.live --list-free               # what costs nothing right now
make live                                      # everything, drafted by a real model
```

**This runs for free.** The default backend is a free model, and the free list
gets queried live rather than hard-coded, because availability changes and a
stale slug in a source file tends to fail at demo time with a confusing 404.

Free models are weaker and rate-limited. For this prototype that's arguably
useful rather than a problem, since a weak model exercises the strict parser and
the gate instead of flattering them. The architectural claim is mostly that the
system stays safe when the model isn't good.

**Rate limits are load, not breakage.** Free tiers are shared pools, so any one
model returns 429 at random times of day with no bearing on your key. The
backend retries once, then falls through a chain of other free models, and the
provenance pin records which one actually answered. Naming a model explicitly
with `--model` turns fallback off, because substituting a different model would
corrupt the experiment that naming one is usually for; `--no-fallback` does the
same when you want the failure loud.

**Provenance pins `model@served_by`, and is built after the answer, never
before.** Both halves matter. Building it before the call would record what we
intended to ask rather than what actually ran, which is wrong whenever the chain
falls back or an alias resolves to a snapshot. And the upstream provider belongs in
the pin because the same slug on two serving stacks can differ in quantisation
and sampling defaults. Before any call `version()` returns a bare slug with no
`@`, so the gate's provenance check rejects a proposal assembled without a real
answer behind it rather than accepting a placeholder that looks like a pin.

**Truncation is reported as ours, not the model's.** A reasoning model spends
the output budget on thinking before it writes a word, and that spend counts
against the same ceiling, measured here at around 1,900 tokens of reasoning on a
routine follow-up. A budget of 2,000 left roughly 80 for the answer and
truncated it mid-JSON, which reaches a strict parser looking much like a model
that can't follow the contract. It's now caught at the backend as
`TruncatedResponse` and tallied separately. Blaming our own config bug on model
quality is the kind of wrong conclusion this prototype is meant to prevent.

There are two backends, which is deliberate rather than indecision. A router
with one implementation behind it is closer to a claim than an architecture:

| Provider | Flag | Notes |
|---|---|---|
| Anthropic | `--provider anthropic` | Needs paid API credits (a Pro subscription is not API access). Official SDK. Constrains the response to a JSON schema at the API level, so a malformed proposal is close to impossible rather than merely caught afterwards. Adaptive thinking on by default; `--no-thinking` is cheaper and faster. |
| OpenRouter (default) | `--provider openrouter` | OpenAI-compatible, stdlib only. Has free models. `--list-free` shows what is free right now. |

Everything downstream is identical across them. Swapping is a flag.

The deterministic reasoner stays the default and CI never calls a model, since a
test suite that costs money per run and varies between runs isn't much of a test
suite.

**The residency guard is the part to look at.** Health data must be processed
in-country and a hosted endpoint is outside that boundary, so the backend
refuses to send any record not marked synthetic, and refuses *before* the
request is built. `is_synthetic` defaults to `False`, i.e. real until proven otherwise, which
seems like the safe direction for that particular flag. There's a test that a
hand-built state can't get exported by accident.

## Demoing it

```bash
make                              # everything, then the clinician surface
python -m tools.demo               # just the surface, when the gates already passed
python -m tools.demo --export demo.html   # one self-contained file you can send
```

There are two pages. `/` is the scripted scenarios, i.e. a record of a run
across both pathways, chosen so that a majority of them refuse. `/clinic` is the
interactive one: generate patients, edit anything about them, paste in a record,
then run the clinician and watch the verdict move. Both drive the identical
pipeline, since a demo whose interactive mode took a different path through the
system would be demonstrating something other than the system.

The clearest thing to show on `/clinic`: take a patient on maximum first-line
therapy with no recent potassium, run it at SITE-A, then run the same patient at
SITE-C. SITE-A asks for the test. SITE-C refers, because it cannot run one. Same
patient, same gap, two right answers, which is gate check 9 earning its place.

While a run is in flight the whole form is locked, and properly disabled rather
than just pointer-events, since CSS stops a mouse but not a keystroke or an
autofill. A result has to describe exactly what was submitted, and a page that
lets you edit a patient mid-run is quietly lying about which patient produced
the verdict.

Each patient shows the phase it's in, reported by the workflow's own `on_step`
callback rather than animated: ELIGIBLE, INTAKE, RECONCILE, PROPOSE (which is
where a live run spends most of its time), then GATE, PRESENT, SIGNED, COMMIT.
`on_step` says what's starting and `trail` says what finished. The two are
deliberately not merged, because conflating them would make a crashed encounter
look like a completed one.

Every result carries its own audit panel (the nine checks with ticks, the path
taken, what the hospital can do, the three provenance pins and the signature),
so "how do I know it actually checked?" is answerable without leaving the page.

**The residency guard is visible there too.** A record is not synthetic unless it
says so, so pasting one in and asking a hosted model to draft it is refused
before any request is built. That refusal appears as a failed visit with its own
words. It is the guard working, and it is worth showing rather than designing
around.

On the scenarios page, two views, and the toggle between them is the whole
argument. **What the
clinician sees** is the consultation surface: on a green visit, no alert at all.
**What the system did** is every check that ran, every finding with its rule id
and citation, the three provenance pins, and the signature record.

The page is generated from a real run and nothing on it is written by hand.
There's a test for that, and another test that it reaches nothing outside
itself. A demo that phones out to a CDN while the document argues for data
residency is the sort of thing this particular audience would notice.

The surface re-reads the packs on every request, so editing a pack file and
refreshing shows the verdict move. That's usually the quickest way to show that
the rules are data rather than code. Python modules are imported once, so a change to
`/service` or `/datagen` needs a restart.

The surface defaults to the **reference reasoner rather than a model**, since
it's free, instant, and identical every run, so a change in behaviour is a real
change rather than the model having a different day. `make live` drafts with an actual
model through the same interface, and nothing downstream moves.

Findings render in English with the deployment language beneath, and none of
that text lives under `/service`. It's the same rule that keeps a drug name out
of the engine, applied to the words a doctor reads. Pack-authored messages
carry a translation directly; messages the engine composes from numbers it
worked out use a pack template with placeholders. Every red flag on both
pathways is translated. A rule with no template shows the engine's English and
an empty second line, which is a visible gap rather than a silent fallback
nobody notices for a year.

Which language leads is one flag, `Labels.english_first`, and it's purely a
display choice (both strings are always carried and no rule reads either). It defaults
to English because the people reading this build are reviewing it, not
practising from it. **A deployed clinic flips it:** a doctor should not read
past a second language to reach the sentence that matters. There is a test for
both directions.

## What the model decides, and what the rules decide

Worth stating plainly, because the division is the whole design and it is easy
to read the wrong way round.

**The model decides what to do.** Assessment, recommendation, which drug at what
dose and schedule, which investigations, the follow-up interval, the patient's
instructions, and its own confidence. That is the clinical plan, not prose.

**And on this pathway the rule engine gets most of it right too.** Measured over
six patients, the reference reasoner and a real model chose the same
recommendation four times. That isn't a failure of the model. It's part of why
adult hypertension follow-up got chosen as V1: it's protocol-dense, and the
escalation ladder more or less *is* the algorithm. The gap shows up in what a
lookup can't produce: on the same six patients the model wrote eight supporting assertions
where the rule engine wrote one, gave a reason a clinician can argue with
("already at the maximum dihydropyridine dose per formulary, further titration
in this class is not permitted") rather than a template, and raised seven
concerns to the rule engine's zero. On the two where they diverged, one was the
model proposing `titrate_down` where the ladder said `continue`.

Worth saying plainly rather than overclaiming: **for a protocol-dense follow-up
pathway, a rule engine is a serious competitor for the decision itself, and the
model is more useful on the parts that aren't a lookup**, i.e. the reasoning,
the patient's own words, and noticing things nobody enumerated. A pathway with
more diagnostic entropy is probably where that balance changes, and this system
doesn't have one yet.

**The rules decide whether that is allowed.** The nine checks, the exclusions,
the red flags. They never choose a plan; they refuse one.

**Escalation is deterministic on purpose.** Red-flag recall is the one number
where a miss can kill someone, and "systolic ≥ 180 with chest pain → alert" is a
lookup with perfect recall on the pattern it names. A model doing that job at
ninety-nine percent is worse, and there isn't much to gain from making a lookup
probabilistic.

**But a rule only catches what somebody enumerated.** Seven red flags is seven
patterns. A patient whose problem isn't one of them gets no flag from the rules,
while the model, having read the whole record, may well have noticed something.
`concerns` is the channel for that:

```
[mention] eGFR has declined steadily from 88 to 64 over the past ~9 months
```

R5 fires on a 30% fall between two readings. Four steps of roughly ten percent
each never trip it, and the rule isn't wrong. It's a threshold, and that's what
thresholds do. The model saw the shape.

**A concern can only add.** It can raise the band (mention to amber, escalate to
red) and it can never lower one, clear an acknowledgement the rules demanded,
turn a refusal into a draft, or mark a patient as fine. That asymmetry is mostly
what makes it safe to let a model speak here at all, since the worst a wrong
concern costs is a clinician's attention. There are tests for each direction.

Making that work needed a fix that turned out to matter more than the feature.
The model was being sent one reading per measurement and then asked to summarise
a trend and notice what the rules don't check for, neither of which is possible
from a single point. This system describes itself as a longitudinal patient
model rather than a conversation, and the longitudinal part was the part the
model never saw. It now gets the recent series per measurement, plus the prior
visits with their decisions.

## Making the drafter better

Three levers, all off by default, all composing through the router as reasoners
wrapping reasoners. Nothing downstream knows they're there, the gate least of
all.

```bash
python -m tools.live --samples 3     # draft it k times, use the agreement
python -m tools.live --critic        # a second model reviews each draft
```

**Self-consistency** (`--samples k`) replaces the model's opinion of itself with
a measurement of its behaviour. Agreement is on the plan rather than the prose,
since two samples that both say titrate up to different doses haven't agreed
about anything a patient would notice. Confidence becomes the minimum of stated
and observed rather than a blend, so neither signal can rescue the other.

**The critic** (`--critic`) catches things rules can't, e.g. a draft that breaks
no rule and is still poor. It may only *lower* confidence. A critic that could
raise it would hold a veto over the abstention floor, which is probably the one
authority nothing here should have. If it fails, the draft continues and gets
marked unreviewed, because an advisory component being down isn't a reason to
deny care, though an unreviewed draft shouldn't look like a reviewed one
either.

**Read-only tools** (`--tools`) let the drafter request what it needs instead of
being handed everything, and record what it asked for. That only works if the
prompt stops pre-loading it. With tools on and the full context still supplied,
a live run requested nothing at all, because there was nothing left to ask for.
Withholding the tool-served material halves the prompt, and the same model then
makes nine to twelve lookups per encounter (and runs slightly faster, since the
prompt is half the size). What a model asks for is itself evidence: one that
titrates a RAAS-acting drug without ever requesting a potassium has told you
something its output never would.

**Schema enforcement** is on by default and steps down cleanly where a provider
will not take it. It is worth having and it is not a defence: asked for a strict
schema, one free model accepted the request and returned a structure of its own
invention. The strict parser remains the thing that actually holds.

**Whether these help is a question, not an assumption.** `python -m tools.concordance`
splits its result by whether the samples agreed, so if unstable drafts are no
likelier to be wrong than stable ones the report says so and recommends dropping
the technique.

Getting an answer took three runs and one corrected mistake.

- **n=30, applied.** Abstention rose from 10% to 23.3%; concordance among
  surviving drafts stayed at 100% either way. It looked like pure cost.
- **The split meant to settle it turned out to be unanswerable.** 23 stable
  drafts and *zero* unstable ones, because agreement feeds the confidence, low
  agreement falls below the abstention floor, and check 8 removes exactly the
  cases the measurement needs. Any conclusion from that run would have been
  circular.
- **n=30, shadow.** Agreement measured but not applied, so unstable drafts
  proceed and can be scored:

  | | drafts | concordant |
  |---|---|---|
  | samples agreed | 19 | **100%** |
  | samples disagreed | 10 | **70%** |

  All three errors in the run were in the unstable group.

- **Replicated on 30 different patients** (`--seed 2000`): stable 23 drafts,
  100% concordant; unstable 6 drafts, 83.3%. The single error was again
  unstable.

Pooled over both runs (58 drafts, 4 errors):

| | drafts | errors |
|---|---|---|
| samples agreed | 42 | **0** |
| samples disagreed | 16 | **4** |

Every error was unstable, and no stable draft was wrong. As a detector,
instability had **100% recall at 25% precision**. If instability were unrelated
to error, the chance of all four landing in the unstable group is **p =
0.0043**, so it's probably not noise.

```bash
python -m tools.concordance --n 30 --live --samples 3 --shadow            # run 1
python -m tools.concordance --n 30 --seed 2000 --live --samples 3 --shadow # run 2
```

That's the trade this system is generally built to take. Abstaining on
instability removed every error at the cost of twelve unnecessary abstentions,
and a wrong draft costs more than no draft in a place where the reviewing doctor
may have nobody to ask.

**What this doesn't show.** The labels come from the reference reasoner, so what
it demonstrates is that instability predicts *divergence from our own rule
engine*, which isn't the same as predicting clinical error. Those only coincide
to the extent the rule engine is right, and that's the question Set C exists to
answer rather than this one. For the same reason self-consistency stays **off by
default**. The evidence is real, but it probably isn't the kind that should
change a default which triples the API calls. Worth re-running on Set C before
promoting it.

## What exists today

The deterministic core, end to end, on synthetic patients:

| Piece | State |
|---|---|
| Indonesia pack: formulary, interactions, guideline, ladder, sites, payer | Real rules, awaiting clinical sign-off |
| Patient state with mandatory provenance | Working |
| Predicate evaluator (fails closed) | Working |
| Eligibility routing: the 7 hard exclusions | Working |
| The nine-check gate | Working |
| Signature line: roster and licence enforced | Working |
| Durable runtime: interrupt / resume / replay | Working. Postgres or files; conformance suite runs against all three implementations |
| Persisted state: checkpoints, signatures, outbound queue | Working. `python -m tools.store`. Both surfaces persist every encounter; `/clinic` restores its patients and verdicts across restarts, and a second run replays rather than re-running |
| Encounter workflow: the full state machine | Working |
| Model router | Interface + deterministic reference reasoner |
| Coding, with evidence on every secondary code | Working |
| FHIR R4 bundle construction | Working. validates clean against the official HL7 R4 validator; builds, does not transmit |
| Offline-first outbound queue, idempotent, file-backed | Working |
| Referral-back draft: the payer's own 3B criteria | Working |
| Synthetic cohort: both pathways, 19 profiles, 19 planted-error mutations | Working |
| Scorecard | 7/7 bars, on the hypertension pathway only |
| EMR adapter | Port defined. Writing one needs access to a real hospital system; the sequencing is BUILD.md Phase 0 |
| Bounded intake interview, in Bahasa Indonesia | Working |
| Pressure suite: 6 patterns x 5 turns, with a control | Working |
| Model-backed reasoner behind the router | Working. needs an API key |
| Residency guard: only synthetic records may leave | Working |
| Medication reconciliation (SPEC §5.3) | Deterministic half working; free-text drug matching still needs a model |
| Clinician presentation layer: the traffic light (SPEC §5.8) | Working |
| Demo surface: clinician view and audit view, from a real run | Working |
| Interactive surface: build/edit patients, 19 profiles, compare across hospitals | Working |
| Between-visit loop (SPEC §5.11) | Schema, provenance and escalation working; patient-facing channel is V1.5 by design |
| Plan-concordance metric (SPEC §8.2) | Working. reported, not gated; needs Set C to mean anything |
| Capability evidence: proof each service was actually delivered | Working |
| Live transport to the national exchange | Bundles build and queue; transmission is blocked on credentials, sandbox only |

**The deterministic core runs with no model involved at all.** Every stage of
`make` except the last one under `make live` never makes an API call. That ordering was on purpose: the
gate is the part that has to be right, it needs nothing else running, and
building it first meant the model arrived into a system that already refused bad
output.

A real model now sits behind the router (`make live`) and changed nothing
downstream: same three-argument signature, same gate, same signature line. That
is the architectural claim discharged rather than asserted. The deterministic
reasoner remains the default, because a test suite that costs money per run and
varies between runs is neither.

## The walkthrough

`make` runs every scripted encounter end to end, across both pathways. A
majority end without a recommendation reaching the doctor, and that ratio is the
point rather than an embarrassment. A demo where the assistant always has an
answer is a demo of a system nobody should deploy.

The last section is not an encounter at all: it pulls the network out mid-clinic,
kills the process, and shows three encounters surviving and syncing without
duplicating. At a site with unreliable power and connectivity that is the normal
case rather than the edge case.

The one worth reading closely is the basic-tier site: a patient who
needs an ACE inhibitor added. Three layers fire at once and agree: the drug
rule wants potassium and eGFR, the sufficiency check says both are absent, and
the capability registry says this hospital cannot run either test. The output is
a referral, not an order nobody can fill.

## The pressure suite

Six pressure patterns, five escalating turns each, in Bahasa Indonesia: the
relative who is a doctor, the herbal remedy that "already worked", the doubled
dose bought at a pharmacy, feeling better and therefore cured, another doctor's
supposedly laxer target, and a demand for a specific drug.

It exists because roughly half of medical model configurations capitulate to a
confidently wrong patient premise within five turns, and there is no equivalent
instrument in Bahasa Indonesia to measure it with.

The shipped surface scores 0%. That number is only worth having because the
suite also runs a **deliberately sycophantic control**, which it catches folding
at turn 3 on every case. A safety test that cannot fail is not a safety test.

And the 0% is honest about what it is: the interviewer scores zero *by
construction*, because it has no clinical voice to be argued out of, rather than
because it was prompted well. The day a model touches patient-facing text it
runs the same suite without that structural advantage.

## Layout

```
packs/id/      the country. Rules as data, versioned, with citations.
               Two pathways live here; adding a third adds no code

service/
  state/       longitudinal patient state, provenance mandatory
  rules/       predicates, target resolution, eligibility, pathway routing
  contracts/   the Proposal: shared vocabulary, owned by neither side
  gate/        the nine checks. stdlib only. no model, ever
  intake/      the bounded interview. structured, never a conversation
  reason/      drafting: prompt, strict parser, schema, reference reasoner,
               self-consistency, critic, read-only tools
  router/      the only place a model provider is named
  reconcile/   record against patient. surfaces, never resolves
  present/     the traffic light. green is silent
  followup/    the between-visit loop
  emit/        coding, FHIR bundles, referral-back, offline queue
  graph/       the only module allowed to import an orchestration library
  packs/       the only module that reads YAML
  signing.py   the signature line

adapters/      EMR ports. Vendor names are allowed here and nowhere else
datagen/       synthetic patients, reference proposer, planted errors
eval/          scorecard, pressure suite, plan concordance
tools/         CI checks, walkthrough, live runner, the demo surface
docs/          every document, including this one
```


## The four rules CI enforces

1. Nothing under `/service` names a country, payer, drug or guideline. The
   banned vocabulary is read from the packs, so adding a drug automatically
   forbids hard-coding it.
2. `/service/gate` imports no orchestration library, no YAML, and nothing from
   `/service/reason`. A test asserts this by inspecting `sys.modules`.
3. Only `/service/graph` imports an orchestration library.
4. No hosted tracing endpoint is configured anywhere.

Rules 1 and 4 are cheap today and impossible to retrofit. Rule 4 is a compliance
landmine, not a preference: tracing is on by default in many setups and would
ship patient data offshore.

## What the scorecard does and does not say

It runs 400 clean cases, 152 planted errors, 120 abstention cases and 140
exclusion cases, and fails the build below any bar.

It proves the pipeline runs and the gate mechanics hold. **It proves nothing
clinical.** Sets A and B are generated from the same guideline the gate checks
against, so a high score is close to tautological. The number that means
something comes from Set C (real retrospective visits, blind-scored by
Indonesian physicians).

**And the bars cover one pathway, not two.** All 152 planted errors are
hypertension mutations (a captopril ceiling, ACEi plus ARB, bisoprolol without
heart failure, etc.), so 7/7 is a statement about hypertension. Diabetes is
covered by the test suite, the FHIR validation and both demo surfaces, and it
is not behind these bars. Extending them means writing a diabetes mutation set,
which is clinical rules work rather than a refactor, and it should probably wait
for the clinical lead who signs the packs off. The scorecard prints both caveats
on every run.

## What survives the process ending

```bash
python -m tools.store                      # what this deployment kept
python -m tools.store --thread <id>        # replay one encounter, step by step
python -m tools.store --signatures         # who signed what, and which draft
python -m tools.store --reset              # destroy all of it and start clean
```

Three things persist (the checkpoints, the signature log and the outbound
queue) and there are two backends behind them. `make` starts Postgres if this
machine has Docker; with nothing reachable the same code writes three
append-only JSONL files under `.store/`. The clinician surface says which one
it used, in its own header, next to the counts.

Both satisfy the same three interfaces, and
[`tests/test_runtime_contract.py`](../tests/test_runtime_contract.py) runs the
same tests against all three implementations: in memory, files, and Postgres.
That's mostly what keeps the choice an implementation detail instead of a fork
in the system's behaviour, and it's why the interface got written before either
backend existed.

**Why a database, given the files already survive a power cut.** Mainly because
append-only stops being a convention and becomes a constraint. A JSONL audit log
is append-only because everyone agrees not to edit it, and any text editor can
rewrite a signature without anything recording that it happened. The migration
installs a trigger that raises on `UPDATE` and `DELETE`, so the rule holds
against the application, against a migration script, and against somebody sitting
at a `psql` prompt. It raises rather than quietly discarding the write, because
an ignored `UPDATE` looks to the caller much like a successful one.
Two smaller reasons: two clinicians on one deployment are two processes
appending to one file, and "which encounters are still unsent" becomes one
statement instead of a full scan.

**Why the files stay.** Roughly one facility in twelve doesn't have power around
the clock, and one in five has unreliable connectivity, so a clinical system that
won't start without a database is one that often doesn't start. `Store` prefers
Postgres, falls back, and says which it picked. Degrading silently would turn
"did that signature persist" into a question nobody thinks to ask.

The schema is in [`db/migrations/`](../db/migrations), numbered and applied in
filename order against a `schema_migrations` tracking table. Postgres also runs
that same directory itself on a fresh container, so the first `docker compose
up` and a later application start converge on the same schema by two different
paths. That's why every statement in a migration is written to be safe to run
twice, and why there's a test for it.

The queue is a log of state transitions rather than a row per item. Enqueue
writes `pending`, a drain writes the outcome, and the current state of an item is
its newest row. An operator at a site with one bar of signal will want to know
how many times a bundle failed and with what error, and a queue that overwrites
its own rows can't tell them.

### The second run picks up where the first stopped

`make` twice does not run `make` twice. Each encounter is stored under a thread
id derived from everything that could change its answer (the scenario, the
patient, the site, the pack and its version, and which drafter is behind the
router), and a run that finds a stored result for the same id replays it instead
of running it again. The page says how many it replayed.

This is what makes the checkpoint do actual work. Without it the durable runtime
writes a record that nothing ever reads back.

It matters most for `make live`, where every encounter is a model call over a
rate-limited free tier. Two of that run's stages call a model (the live runner
and the clinician surface) and both resume:

| | first run | second run |
|---|---|---|
| `make`, 9 scripted encounters | run | replayed, 0 model calls |
| `make live`, live runner (5) + surface (9) | 14 model calls | **0** |

Measured on the surface alone: 3m28s, then 1.1s, with identical outcomes. The
live runner marks every replayed line with `[replayed from the store, no model
call]`, and closes with a count of how many were replayed against how many calls
were made. A replayed encounter that read like a fresh one would be a demo
claiming an API call it didn't make, and that stage exists mostly to show the
model is real.

**A failure isn't an answer.** An encounter whose response didn't parse, or that
got rate-limited, stores nothing, so the next run calls the model for it again.
Storing failures would replay them forever and never retry the call that might
succeed.

The risk a cache introduces is showing an answer to a question nobody asked, so
the invalidation is the part worth reading. Edit a guideline file and the pack
version moves, so every encounter runs again, which keeps the "edit a pack,
refresh, watch the verdict move" property intact. Swap the reference reasoner
for a real model and everything re-runs, because a page drafted by plain code
shouldn't be served as though a model had written it. Build a different patient
in `/clinic` and it's a different encounter.

Two escapes, both deliberate:

```bash
CLINICIAN_FRESH=1 make live     # re-run everything even if it is stored
CLINICIAN_STORE_BACKEND=files make   # ignore the database, use .store/
```

`CLINICIAN_FRESH` exists because watching a live model disagree with itself
across runs is a reasonable thing to want, and it's the thing resumption
otherwise hides.

**`/clinic` restores but never resumes**, and the two are different things.

*Resuming* would mean pressing Run and getting an earlier answer back. It does
not do that. The scripted page is a *report* of a run, so serving a stored one
is right; a patient you built and ran with a button is an *action*, and an
action that silently hands back an earlier answer looks broken, especially on
camera, with a live model that was expected to visibly think. Two runs of the
same record at different times are also genuinely two encounters, so they get
two thread ids rather than one overwriting the other.

*Restoring* is what happens when you open the page. Everything run there in
earlier sessions comes back (the patients as editable records, with their
verdicts, signatures and codes), read from the store by `/api/history`. This
was the one part of the system that kept nothing: results lived in a dict in
the server process and patients lived in the browser tab, so closing either one
lost the work. They had been written to the store the whole time; nothing was
reading them back.

Only the newest run of a record gets a card, because re-running a patient is
that patient seen again rather than a second patient. Every run stays on the
record and stays replayable with `python -m tools.store --thread <id>`.

**Clearing the list deletes nothing.** The store refuses `UPDATE` and `DELETE`,
so "Clear this list" writes a marker forward and the page starts after it. An
audit log with a working clear button wouldn't be much of an audit log, and this is
the append-only constraint being designed around rather than fought, which is
the more useful thing to show someone than the trigger itself.

### Starting completely fresh

```bash
python -m tools.store --reset     # asks first; --yes to skip the prompt
```

This is the one thing in the codebase that suspends the append-only triggers,
and it is deliberately a command a person types rather than anything a run can
reach. It prints what it is about to destroy and waits for you to type `yes`,
because "start afresh before a recording" and "delete the signatures a licensed
doctor put their name to" are the same keystroke here.

It is **not** what `/clinic`'s *Clear this list* does. That writes a marker
forward and destroys nothing, which is the behaviour the product has. `--reset`
is the operator's hammer, and it exists because a prototype's store fills with
synthetic demo runs. In a real deployment I don't think it would ship, since destroying a
clinical audit trail is unlawful, not merely inadvisable.

It works on both backends, so a developer on files does not learn a different
command from one on Postgres. There is a test that it puts the triggers back
afterwards: a reset that left them off would turn the store's central guarantee
into something that held only until the first time somebody started clean, and
it would hide, because an append-only table behaves exactly like a mutable one
right up until someone mutates it.

One known limit, stated rather than discovered later: the runtime loads a
deployment's checkpoints once per process, so a store with tens of thousands of
encounters in it would make startup slow and memory-hungry. A targeted query
per lookup is the fix, and it is not written because a demo store holds
hundreds. It becomes real the moment this runs somewhere that is not a demo.

Deriving the key was the fiddly part, and two versions of it were wrong:

- Keying on `backend.version()` looked obvious and never resumed anything. A
  hosted backend rewrites that string to `model@served_by` once it has an
  answer, so the first encounter of a run and the second had different keys.
- Falling back to `"reference"` when the router could not name a backend put
  two different drafters in one bucket, since that string is how the reference
  reasoner reports itself, so a router that raised for an unrelated reason
  (one that fails every draft, in the test that caught it) replayed the
  reference reasoner's *successful* results and the page reported zero
  failures. The router's class is part of the key now. Failing to name a
  backend is not itself a name.

This was missing, and its absence made two claims false rather than merely
incomplete. A checkpoint is supposed to be a recovery point for *service
restart*, and about one facility in twelve lacks 24-hour power, so the process
dying is the ordinary case. And replay is supposed to be the answer when a
regulator asks why the system said something, which needs the record to
outlive the process that made it. The signature is the artefact that makes an
output lawful and it was the least durable thing in the system.

A signature now carries its provenance to disk, so the question "which model,
which prompt, which rule set did this person put their licence behind" has an
answer months later:

```
2026-08-29 10:00:00  PRAC-A-001 (internist)  accepted
  signed a draft from minimax/minimax-m3:free@GMICloud | htn-followup@0.2.0 | id-htn-2026-08@1
```

Turning persistence on immediately found a bug that was invisible without it:
thread ids were built from a position in a run, so two runs both used `LIVE-0`
and appended two different encounters to one audit trail. A corrupted record is
worse than no record.

## Conformance

```bash
python -m tools.validate_fhir --download   # once: ~190 MB into .tools/
python -m tools.validate_fhir              # also runs as a stage of `make`
```

The validator is a Java distribution, so it is gitignored rather than vendored
since it's the same file for everyone and doesn't belong in a repository. A
missing validator is a missing prerequisite, not a failure: the stage says
which command to run and exits cleanly. `FHIR_VALIDATOR_JAR` overrides the
location. Four bundles (both pathways, controlled and uncontrolled, three
different sites) validate with **0 errors** against FHIR R4.

There is also a hand-written conformance test that runs in CI with no download.
It is worth having and it is not a substitute: the real validator found nine
errors it had missed, including one the hand-written test had *introduced*.
Approximating a specification is not the same as checking against it. What it
caught:

- every `fullUrl` read `urn:uuid:ENC-1`, which is not a UUID
- fixing that broke bundle reference resolution, because internal references
  must use the urn once `fullUrl` is one
- two codes carried a `display` that was not the code's registered name
- a blood pressure was emitted as two Observations, when the FHIR blood-pressure
  profile wants one panel with two components, so six errors came from one mistake
- `Observation.category` was missing the vital-signs slice the profile requires
- the generator produced `E11.65`, which is ICD-10-CM (US) and does not exist in
  the WHO ICD-10 that Indonesia codes against

Remaining warnings are best-practice recommendations (narrative text, UCUM
annotations) rather than conformance failures.

## What is left, and none of it is code

Every pathway step in SPEC-V1 §5 is built and tested. What remains needs
somebody this project does not have, and no amount of engineering substitutes
for any of it.

1. **A clinical lead with STR + SIP** to sign the packs off against primary
   sources and answer the nine questions in SPEC-V1 §10. Three blood-pressure
   targets are missing today and the system correctly abstains on those
   subgroups until they exist. Nothing here is clinically active while
   `review.status` reads `awaiting_clinical_signoff`.
2. **Set C**, i.e. 300 real visits, physician-adjudicated. Every number this
   repository produces is caveated on it. The loader and the metric are
   finished, so scoring it is a command; obtaining it is a clinical and legal
   exercise.
3. **The real hospital system**, standing up from its own migrations against a
   seeded database, to time the panel round trip and resolve assumption A1
   properly. One engineer, two days, per the assumption register.
4. **A pharmacist** to verify 200 formulary rows against the decree, resolving
   A4.

The honest summary is that the engineering question (can a system draft safely,
refuse well, and stay pathway- and country-agnostic) has been answered as far
as synthetic patients can answer it. The clinical question has not been
touched, and asking a repository to answer it would be a category error.
