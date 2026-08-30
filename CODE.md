# The prototype

The code that implements [SPEC-V1.md](SPEC-V1.md). Start here if you are
building; start at [README.md](README.md) if you are deciding.

```bash
make install    # venv + two dependencies
make all        # checks, tests, scorecard, pressure suite — what CI runs
make demo       # six scripted encounters, plus the network dropping
make pressure   # the Bahasa Indonesian pressure suite
make prompt     # print the exact prompt sent to a model (no key needed, no spend)
make live       # 5 encounters through a real model (needs a key, costs money)
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
| FHIR R4 bundle construction | Working — builds, does not transmit |
| Offline-first outbound queue, idempotent, file-backed | Working |
| Referral-back draft — the payer's own 3B criteria | Working |
| Synthetic patients, 19 planted-error mutations | Working |
| Scorecard | 7/7 bars |
| EMR adapter | Interface only — deliberately raises |
| Bounded intake interview, in Bahasa Indonesia | Working |
| Pressure suite — 6 patterns x 5 turns, with a control | Working |
| Model-backed reasoner behind the router | Working — needs an API key |
| Residency guard: only synthetic records may leave | Working |
| Medication reconciliation | Not started |
| Live transport to the national exchange | Not started — no credentials, sandbox only |

**No model is involved anywhere yet.** That is on purpose: the gate is the part
that has to be right, it needs nothing else running, and building it first means
the model arrives into a system that already refuses bad output.

## The walkthrough

`make demo` runs six encounters end to end. Four of them end without a
recommendation — a handoff, two refusals and an escalation — and that ratio is
the point rather than an embarrassment. A demo where the assistant always has an
answer is a demo of a system nobody should deploy.

The seventh is not an encounter at all: it pulls the network out mid-clinic,
kills the process, and shows three encounters surviving and syncing without
duplicating. At a site with unreliable power and connectivity that is the normal
case rather than the edge case.

The one worth reading closely is the sixth: a patient at a basic-tier site who
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
packs/id/      the country. Rules as data, versioned, with citations
service/
  state/       longitudinal patient state, provenance mandatory
  rules/       predicate evaluator, target resolution, eligibility
  contracts/   the Proposal — shared vocabulary, owned by neither side
  gate/        the nine checks. stdlib only. no model, ever
  graph/       the only module allowed to import an orchestration library
  packs/       the only module that reads YAML
  signing/     the signature line
adapters/      EMR ports. Vendor names are allowed here and nowhere else
datagen/       synthetic patients, reference proposer, planted errors
eval/          the scorecard
tools/         architectural checks that run in CI
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

## Next

1. Stand up the real hospital system with a seeded database and time the panel
   round trip. Resolves assumption A1 properly.
2. Parse the formulary decree into the pack and have a pharmacist verify 200
   rows. Resolves A4.
3. Put a real model behind the router. It implements the same three-argument
   signature as the reference reasoner, and the gate does not change.
4. Get the clinical lead to answer the nine open questions in SPEC-V1 §10 —
   three BP targets are blocking whole patient subgroups today, and the system
   correctly abstains on all of them until then.
