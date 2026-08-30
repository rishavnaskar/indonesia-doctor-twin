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
pip install -r requirements-model.txt          # optional extra, not core
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env    # .env is gitignored
make live
```

Two backends exist, and that is the point rather than indecision — a router
with one implementation is a claim, not an architecture:

| Provider | Flag | Notes |
|---|---|---|
| Anthropic (default) | `--provider anthropic` | Official SDK. Constrains the response to a JSON schema at the API level, so a malformed proposal is close to impossible rather than merely caught afterwards. Adaptive thinking on by default; `--no-thinking` is cheaper and faster. |
| OpenRouter | `--provider openrouter` | OpenAI-compatible, stdlib only. Useful for comparing models across vendors. |

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
