# The prototype

The code that implements [SPEC-V1.md](SPEC-V1.md). Start here if you are
building; start at [README.md](../README.md) if you are deciding.

```bash
make install       # venv + two runtime dependencies
make all           # checks, tests, scorecard, pressure suite — what CI runs
make e2e           # all of the above, then the walkthrough and live encounters

make demo          # the scripted encounters in the terminal, plus the network dropping
make surface       # the clinician surface in a browser; /clinic is the interactive one
make page          # one self-contained HTML file you can send to someone

make pressure      # the Bahasa Indonesian pressure suite
make concordance   # plan concordance (SPEC §8.2) — reported, never gated
make prompt        # print the exact prompt sent to a model (no key, no spend)
make free          # which models cost nothing right now
make live          # encounters through a real model (needs a key; free by default)
make surface-live  # the surface, drafted by a real model
```

### Running against a real model

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' >> .env    # .env is gitignored
make free                                      # what costs nothing right now
make live                                      # 5 encounters, free model
```

**This runs for free.** The default backend is a free model, and the free list
is queried live rather than hard-coded — availability changes, and a stale slug
in a source file fails at demo time with a confusing 404.

Free models are weaker and rate-limited. For this prototype that is closer to a
feature than a problem: a weak model exercises the strict parser and the gate
instead of flattering them, and the whole architectural claim is that the system
stays safe when the model is not good.

**Rate limits are load, not breakage.** Free tiers are shared pools, so any one
model returns 429 at random times of day with no bearing on your key. The
backend retries once, then falls through a chain of other free models, and the
provenance pin records which one actually answered. Naming a model explicitly
with `--model` turns fallback off, because substituting a different model would
corrupt the experiment that naming one is usually for; `--no-fallback` does the
same when you want the failure loud.

**Provenance pins `model@served_by`, and is built after the answer, never
before.** Both halves are load-bearing. Building it before the call would record
what we intended to ask rather than what ran — wrong whenever the chain falls
back or an alias resolves to a snapshot. And the upstream provider belongs in
the pin because the same slug on two serving stacks can differ in quantisation
and sampling defaults. Before any call `version()` returns a bare slug with no
`@`, so the gate's provenance check rejects a proposal assembled without a real
answer behind it rather than accepting a placeholder that looks like a pin.

**Truncation is reported as ours, not the model's.** A reasoning model spends
the output budget on thinking before it writes a word, and that spend counts
against the same ceiling — measured here at ~1,900 tokens of reasoning on a
routine follow-up. A budget of 2,000 left ~80 for the answer and truncated it
mid-JSON, which reaches a strict parser looking exactly like a model that cannot
follow the contract. It is now caught at the backend as `TruncatedResponse` and
tallied separately. Misattributing our config bug to model quality is the class
of wrong conclusion this prototype exists to prevent.

Two backends exist, and that is the point rather than indecision — a router
with one implementation is a claim, not an architecture:

| Provider | Flag | Notes |
|---|---|---|
| Anthropic | `--provider anthropic` | Needs paid API credits (a Pro subscription is not API access). Official SDK. Constrains the response to a JSON schema at the API level, so a malformed proposal is close to impossible rather than merely caught afterwards. Adaptive thinking on by default; `--no-thinking` is cheaper and faster. |
| OpenRouter (default) | `--provider openrouter` | OpenAI-compatible, stdlib only. Has free models. `--list-free` shows what is free right now. |

Everything downstream is identical across them. Swapping is a flag.

The deterministic reasoner stays the default, and CI never calls a model — a
test suite that costs money per run and varies between runs is neither.

**The residency guard is the part to look at.** Health data must be processed
in-country and a hosted endpoint is outside that boundary, so the backend
refuses to send any record not marked synthetic, and refuses *before* the
request is built. `is_synthetic` defaults to `False`: real-until-proven-
otherwise is the safe direction for that particular flag. There is a test that a
hand-built state cannot be exported by accident.

## Demoing it

```bash
make surface                      # the clinician surface, localhost
make page                         # one self-contained file you can send
python -m tools.demo --live       # drive the same scenarios with a real model
```

There are two pages. `/` is the scripted scenarios — a record of a run across
both pathways, chosen so that a majority of them refuse. `/clinic` is interactive: generate
patients, edit anything about them, paste in a record, then run the clinician
and watch the verdict move. Both drive the identical pipeline; a demo whose
interactive mode took a different path through the system would be
demonstrating something other than the system.

The clearest thing to show on `/clinic`: take a patient on maximum first-line
therapy with no recent potassium, run it at SITE-A, then run the same patient at
SITE-C. SITE-A asks for the test. SITE-C refers, because it cannot run one. Same
patient, same gap, two right answers — that is gate check 9 earning its place.

While a run is in flight the whole form is locked — really disabled, not just
pointer-events, since CSS stops a mouse but not a keystroke or an autofill. A
result must describe exactly what was submitted, and a page that lets you edit
a patient mid-run is quietly lying about which patient produced the verdict.

Each patient shows the phase it is actually in, reported by the workflow's own
`on_step` callback rather than animated: ELIGIBLE, INTAKE, RECONCILE, PROPOSE —
which is where a live run spends its time — then GATE, PRESENT, SIGNED, COMMIT.
`on_step` says what is starting; `trail` says what finished, and the two are
deliberately not merged, because conflating them would make a crashed encounter
look like a completed one.

Every result carries its own audit panel — the nine checks with ticks, the path
taken, what the hospital can do, the three provenance pins and the signature —
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
There is a test for that, and a test that it reaches nothing outside itself — a
demo that phones out to a CDN while the document argues for data residency is an
own goal in front of exactly the audience that will notice.

`make surface` re-reads the packs on every request, so editing a pack file and
refreshing shows the verdict move — the fastest way to demonstrate that the rules
are data rather than code. Python modules are imported once, so a change to
`/service` or `/datagen` needs a restart.

The surface defaults to the **reference reasoner, not a model**: free, instant,
and identical every run, so a change in behaviour is a real change rather than
the model having a different day. `make surface-live` drafts with an actual
model through the same interface, and nothing downstream moves.

Findings render in English with the deployment language beneath, and none of
that text lives under `/service` — the same rule that keeps a drug name
out of the engine, applied to the words a doctor reads. Pack-authored messages
carry a translation directly; messages the engine composes from numbers it
worked out use a pack template with placeholders. Every red flag on both
pathways is translated. A rule with no template shows the engine's English and
an empty second line, which is a visible gap rather than a silent fallback
nobody notices for a year.

Which language leads is one flag, `Labels.english_first`, and it is a display
choice — both strings are always carried and no rule reads either. It defaults
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

**The rules decide whether that is allowed.** The nine checks, the exclusions,
the red flags. They never choose a plan; they refuse one.

**Escalation is deterministic on purpose.** Red-flag recall is the one number
where a miss can kill someone, and "systolic ≥ 180 with chest pain → alert" is a
lookup with perfect recall on the pattern it names. A model doing that job at
ninety-nine percent is strictly worse, and there is nothing to gain by making a
lookup probabilistic.

**But a rule only catches what somebody enumerated.** Seven red flags is seven
patterns. A patient whose problem is not one of them gets no flag from the
rules — while the model, having read the whole record, may well have noticed.
`concerns` is the channel for that:

```
[mention] eGFR has declined steadily from 88 to 64 over the past ~9 months
```

R5 fires on a 30% fall between two readings. Four steps of roughly ten percent
each never trip it, and the rule is not wrong — it is a threshold, and that is
what thresholds do. The model saw the shape.

**A concern can only add.** It raises the band — mention to amber, escalate to
red — and can never lower one, clear an acknowledgement the rules demanded, turn
a refusal into a draft, or mark a patient as fine. That asymmetry is what makes
it safe to let a model speak here at all: the worst a wrong concern costs is a
clinician's attention. There are tests for each direction.

Making that work needed a fix that mattered more than the feature. The model was
being sent one reading per measurement and then asked to summarise a trend and
notice what the rules do not check for — both impossible from a single point.
This system describes itself as a longitudinal patient model rather than a
conversation, and the longitudinal part was the part the model never saw. It now
receives the recent series per measurement and the prior visits with their
decisions.

## Making the drafter better

Three levers, all off by default, all composing through the router as reasoners
wrapping reasoners. Nothing downstream — the gate least of all — knows they are
there.

```bash
python -m tools.live --samples 3     # draft it k times, use the agreement
python -m tools.live --critic        # a second model reviews each draft
```

**Self-consistency** (`--samples k`) replaces the model's opinion of itself with
a measurement of its behaviour. Agreement is on the plan, not the prose — two
samples that both say titrate up to different doses have not agreed about
anything a patient would notice. Confidence becomes the minimum of stated and
observed, never a blend, so neither signal can rescue the other.

**The critic** (`--critic`) catches what rules cannot: a draft that breaks no
rule and is still poor. It may only *lower* confidence. A critic that could
raise it would hold a veto over the abstention floor, which is the one authority
nothing here may have. If it fails, the draft continues and is marked
unreviewed — an advisory component being down is not a reason to deny care, but
an unreviewed draft must never look like a reviewed one.

**Read-only tools** (`--tools`) let the drafter request what it needs instead of
being handed everything, and record what it asked for. That only works if the
prompt stops pre-loading it: with tools on and the full context still supplied,
a live run requested nothing at all, because there was nothing left to ask for.
Withholding the tool-served material halves the prompt, and the same model then
makes nine to twelve lookups per encounter — and runs slightly faster, because
the prompt is half the size. What a model asks for is evidence: one that
titrates a RAAS-acting drug without ever requesting a potassium has told you
something its output never would.

**Schema enforcement** is on by default and steps down cleanly where a provider
will not take it. It is worth having and it is not a defence: asked for a strict
schema, one free model accepted the request and returned a structure of its own
invention. The strict parser remains the thing that actually holds.

**Whether these help is a question, not an assumption.** `make concordance`
splits its result by whether the samples agreed, so if unstable drafts are no
likelier to be wrong than stable ones the report says so and recommends dropping
the technique.

Getting an answer took three runs and one corrected mistake.

- **n=30, applied.** Abstention rose from 10% to 23.3%; concordance among
  surviving drafts stayed at 100% either way. It looked like pure cost.
- **The split meant to settle it was unanswerable.** 23 stable drafts, *zero*
  unstable ones — because agreement feeds the confidence, low agreement falls
  below the abstention floor, and check 8 removes exactly the cases the
  measurement needs. Any conclusion from that run would have been circular.
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

Pooled over both runs — 58 drafts, 4 errors:

| | drafts | errors |
|---|---|---|
| samples agreed | 42 | **0** |
| samples disagreed | 16 | **4** |

Every error was unstable; no stable draft was wrong. As a detector, instability
had **100% recall at 25% precision**. If instability were unrelated to error,
the chance of all four landing in the unstable group is **p = 0.0043**, so this
is not noise.

```bash
python -m tools.concordance --n 30 --live --samples 3 --shadow            # run 1
python -m tools.concordance --n 30 --seed 2000 --live --samples 3 --shadow # run 2
```

That trade is the one this system is built to take: abstaining on instability
removes every error at the cost of twelve unnecessary abstentions, and a wrong
draft costs more than no draft where the reviewing doctor may have nobody to
ask.

**What this does not show.** The labels come from the reference reasoner, so
what is demonstrated is that instability predicts *divergence from our own rule
engine* — not that it predicts clinical error. Those coincide only to the extent
the rule engine is right, which is the question Set C exists to answer and this
cannot. For the same reason self-consistency stays **off by default**: the
evidence is real but it is not the kind of evidence that should change a default
which triples the API calls. Re-run it on Set C before promoting it.

## What exists today

The deterministic core, end to end, on synthetic patients:

| Piece | State |
|---|---|
| Indonesia pack — formulary, interactions, guideline, ladder, sites, payer | Real rules, awaiting clinical sign-off |
| Patient state with mandatory provenance | Working |
| Predicate evaluator (fails closed) | Working |
| Eligibility routing — the 7 hard exclusions | Working |
| The nine-check gate | Working |
| Signature line — roster and licence enforced | Working |
| Durable runtime interface — interrupt / resume / replay | Reference implementation |
| Encounter workflow — the full state machine | Working |
| Model router | Interface + deterministic reference reasoner |
| Coding, with evidence on every secondary code | Working |
| FHIR R4 bundle construction | Working — validates clean against the official HL7 R4 validator; builds, does not transmit |
| Offline-first outbound queue, idempotent, file-backed | Working |
| Referral-back draft — the payer's own 3B criteria | Working |
| Synthetic cohort — both pathways, 19 profiles, 19 planted-error mutations | Working |
| Scorecard | 7/7 bars |
| EMR adapter | Port defined. Writing one needs access to a real hospital system; the sequencing is BUILD.md Phase 0 |
| Bounded intake interview, in Bahasa Indonesia | Working |
| Pressure suite — 6 patterns x 5 turns, with a control | Working |
| Model-backed reasoner behind the router | Working — needs an API key |
| Residency guard: only synthetic records may leave | Working |
| Medication reconciliation (SPEC §5.3) | Deterministic half working; free-text drug matching still needs a model |
| Clinician presentation layer — the traffic light (SPEC §5.8) | Working |
| Demo surface — clinician view and audit view, from a real run | Working |
| Interactive surface — build/edit patients, 19 profiles, compare across hospitals | Working |
| Between-visit loop (SPEC §5.11) | Schema, provenance and escalation working; patient-facing channel is V1.5 by design |
| Plan-concordance metric (SPEC §8.2) | Working — reported, not gated; needs Set C to mean anything |
| Capability evidence — proof each service was actually delivered | Working |
| Live transport to the national exchange | Bundles build and queue; transmission is blocked on credentials, sandbox only |

**The deterministic core runs with no model involved at all** — `make checks
test score pressure` never makes an API call. That ordering was on purpose: the
gate is the part that has to be right, it needs nothing else running, and
building it first meant the model arrived into a system that already refused bad
output.

A real model now sits behind the router (`make live`) and changed nothing
downstream — same three-argument signature, same gate, same signature line. That
is the architectural claim discharged rather than asserted. The deterministic
reasoner remains the default, because a test suite that costs money per run and
varies between runs is neither.

## The walkthrough

`make demo` runs every scripted encounter end to end, across both pathways. A
majority end without a recommendation reaching the doctor, and that ratio is the
point rather than an embarrassment. A demo where the assistant always has an
answer is a demo of a system nobody should deploy.

The last section is not an encounter at all: it pulls the network out mid-clinic,
kills the process, and shows three encounters surviving and syncing without
duplicating. At a site with unreliable power and connectivity that is the normal
case rather than the edge case.

The one worth reading closely is the basic-tier site: a patient who
needs an ACE inhibitor added. Three layers fire at once and agree — the drug
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
construction*, because it has no clinical voice to be argued out of — not
because it was prompted well. The day a model touches patient-facing text it
runs the same suite without that structural advantage.

## Layout

```
packs/id/      the country. Rules as data, versioned, with citations.
               Two pathways live here; adding a third adds no code

service/
  state/       longitudinal patient state, provenance mandatory
  rules/       predicates, target resolution, eligibility, pathway routing
  contracts/   the Proposal — shared vocabulary, owned by neither side
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
  signing/     the signature line

adapters/      EMR ports. Vendor names are allowed here and nowhere else
datagen/       synthetic patients, reference proposer, planted errors
eval/          scorecard, pressure suite, plan concordance
tools/         CI checks, walkthrough, live runner, the demo surface
docs/          every document, including this one
```


## The four rules CI enforces

1. Nothing under `/service` names a country, payer, drug or guideline — the
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
something comes from Set C — real retrospective visits, blind-scored by
Indonesian physicians. The scorecard prints this caveat on every run.

## Conformance

```bash
make fhir-setup   # once: downloads the validator (~190 MB) into .tools/
make fhir         # the official HL7 validator over the emitted bundles
```

The validator is a Java distribution, so it is gitignored rather than vendored
— it is the same file for everyone and does not belong in a repository. A
missing validator is a missing prerequisite, not a failure: `make fhir` says
which command to run and exits cleanly. `FHIR_VALIDATOR_JAR` overrides the
location. Four bundles — both pathways, controlled and uncontrolled, three
different sites — validate with **0 errors** against FHIR R4.

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
  profile requires one panel with two components — six errors from one mistake
- `Observation.category` was missing the vital-signs slice the profile requires
- the generator produced `E11.65`, which is ICD-10-CM (US) and does not exist in
  the WHO ICD-10 that Indonesia codes against

Remaining warnings are best-practice recommendations — narrative text, UCUM
annotations — not conformance failures.

## What is left, and none of it is code

Every pathway step in SPEC-V1 §5 is built and tested. What remains needs
somebody this project does not have, and no amount of engineering substitutes
for any of it.

1. **A clinical lead with STR + SIP** to sign the packs off against primary
   sources and answer the nine questions in SPEC-V1 §10. Three blood-pressure
   targets are missing today and the system correctly abstains on those
   subgroups until they exist. Nothing here is clinically active while
   `review.status` reads `awaiting_clinical_signoff`.
2. **Set C** — 300 real visits, physician-adjudicated. Every number this
   repository produces is caveated on it. The loader and the metric are
   finished, so scoring it is a command; obtaining it is a clinical and legal
   exercise.
3. **The real hospital system**, standing up from its own migrations against a
   seeded database, to time the panel round trip and resolve assumption A1
   properly. One engineer, two days, per the assumption register.
4. **A pharmacist** to verify 200 formulary rows against the decree, resolving
   A4.

The honest summary: the engineering question — can a system draft safely,
refuse well, and stay pathway- and country-agnostic — has been answered as far
as synthetic patients can answer it. The clinical question has not been
touched, and asking a repository to answer it would be a category error.
