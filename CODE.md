# The prototype

The code that implements [SPEC-V1.md](SPEC-V1.md). Start here if you are
building; start at [README.md](README.md) if you are deciding.

```bash
make install    # venv + two dependencies
make all        # architectural checks, tests, scorecard — what CI runs
```

## What exists today

The deterministic core, end to end, on synthetic patients:

| Piece | State |
|---|---|
| Indonesia pack — formulary, interactions, guideline, sites, payer | Real rules, awaiting clinical sign-off |
| Patient state with mandatory provenance | Working |
| Predicate evaluator (fails closed) | Working |
| Eligibility routing — the 7 hard exclusions | Working |
| The nine-check gate | Working |
| Signature line — roster and licence enforced | Working |
| Durable runtime interface — interrupt / resume / replay | Reference implementation |
| Synthetic patients, reference proposer, 19 planted-error mutations | Working |
| Scorecard | 7/7 bars |
| EMR adapter | Interface only — deliberately raises |
| Model, retrieval, coding, FHIR emission | Not started |

**No model is involved anywhere yet.** That is on purpose: the gate is the part
that has to be right, it needs nothing else running, and building it first means
the model arrives into a system that already refuses bad output.

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
3. Put a real model behind the router, implementing the same proposer
   interface. The gate does not change.
4. Get the clinical lead to answer the nine open questions in SPEC-V1 §10 —
   three BP targets are blocking whole patient subgroups today, and the system
   correctly abstains on all of them until then.
