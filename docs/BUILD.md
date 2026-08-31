# Building It, End to End

A prototype plan. What we build, in what order, and what we make up versus what we get for real.

*Companion documents: [DECISION.md](DECISION.md) for the case in twelve minutes, [RESEARCH.md](RESEARCH.md) for the evidence and sources, and **[SPEC-V1.md](SPEC-V1.md)** for the first pathway specified end to end, which is the one an engineer starts from.*

---

## 1. The short answer on data

**Yes, we assume the patient history, and I think that's fine as long as we're loud about it.**

We have no client, no hospital, and no lawful basis to touch a real Indonesian medical record. Indonesian law (UU PDP 27/2022) treats health data as sensitive and requires an explicit lawful basis, and GR 28/2024 requires it to stay inside the country. So real patient data is out, and pretending otherwise would be the fastest way to fail this on ethics rather than engineering.

What matters is being precise about which parts are fake. Most of the system is not.

| Component | Real or synthetic | Notes |
|---|---|---|
| Hospital system (SIMRS) | **Real** | SIMRS Khanza is open source. We run the actual software Indonesian hospitals use. |
| National formulary (Fornas) | **Real** | Published as a ministerial decree. We parse it. |
| Clinical guidelines (PNPK / PPK) | **Real** | Published by Kemenkes and IDI. |
| ICD-10 / ICD-9-CM | **Real** | Standard. |
| SATUSEHAT integration | **Real** | Public developer portal, OAuth2, FHIR R4. Test against their sandbox. |
| Chest X-rays for TB | **Real** | Public research datasets exist (Shenzhen, Montgomery, NIH). |
| **Patient records** | **Synthetic** | Generated. This is the big assumption. |
| **Consultation audio** | **Synthetic** | We script and record it ourselves. |
| **Per-site drug stock** | **Synthetic** | We invent a plausible stock list from Fornas. |

So the honest framing: **the pipes are real, the patients are not.** That is a normal way to build a clinical prototype and it is what we say on the first slide.

### How we generate the patients

Three layers, in this order:

1. **Synthea** (MITRE's open-source synthetic patient generator) for the skeleton: demographics, longitudinal visit structure, labs over time. It ships US-shaped, so we re-weight it: Indonesian age pyramid, Indonesian disease mix (URI, TB, dengue, hypertension, type 2 diabetes), Indonesian names, BPJS membership.
2. **Guideline-grounded case generation.** We take the real PNPK/PPK documents and generate cases *from* them, so every synthetic patient has a known-correct answer we can score against. That gives us a gold standard on day one, which is otherwise the sort of thing you'd have to buy from a panel of doctors.
3. **Deliberately broken cases.** For every clean case we generate a corrupted twin: wrong drug, missed red flag, dose out by 10x, a contraindication ignored, etc. Those are the test set for the safety gate. If the gate can't catch errors we planted ourselves, it probably won't catch real ones.

Roughly 1,000 clean cases and 300 broken ones is enough for a prototype.

### What synthetic data can and cannot prove

**It can prove:** the pipeline runs end to end; the safety gate catches known errors; the output is valid FHIR that SATUSEHAT accepts; coding matches the gold standard; latency and cost are workable; the model holds its position under patient pressure.

**It cannot prove:** real diagnostic accuracy, real time saved, real error reduction, or that doctors will use it. Those need real patients and are the reason the 90-day plan starts with a stopwatch in a real hospital.

Say both parts out loud. A prototype that overclaims is worse than one that underdelivers.

---

## 2. The stack

Nothing exotic. The interesting choices are Khanza and the split between the model and the gate.

```
┌─────────────────────────────────────────────────────┐
│  SIMRS Khanza (Docker)          ← the "hospital"    │
│  Java client + MySQL                                │
│  our panel injected into the consultation form      │
└────────────────────┬────────────────────────────────┘
                     │ MySQL + REST
┌────────────────────▼────────────────────────────────┐
│  Our service (Python / FastAPI)                     │
│                                                     │
│  intake ──► patient state ──► reasoning ──► GATE ──►│
│                    ▲                          │     │
│                    │                          ▼     │
│              retrieval                   traffic    │
│         (PNPK · PPK · Fornas)              light    │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   FHIR R4 bundle            eval harness
   → SATUSEHAT sandbox       → scorecard
```

> **Status in the prototype: the top box is not built, and neither is the
> arrow to SATUSEHAT.** This is the plan's stack, not a picture of what runs
> today. What runs is the middle box and the two boxes under it: intake,
> patient state, reasoning, the gate, the traffic light, FHIR bundle
> construction and the eval harness, on synthetic patients, with Postgres
> holding the state.
>
> The hospital system is absent because standing one up needs a real
> deployment to read from, which is Phase 0 below and the thing that resolves
> assumption A1. In its place `adapters/base.py` defines the port every
> hospital system goes through, with no implementations behind it, and CI
> fails the build if anything under `/service` so much as names a vendor. So
> the commitment is the interface, and the first adapter is still work nobody
> has done.
>
> The FHIR bundles build and validate clean against the official HL7 R4
> validator. Nothing is transmitted: that needs credentials for the national
> exchange, which needs an organisation that has them.

**Choices worth defending:**

- **Khanza in Docker.** It is the real system, it is open source, and it already has a `src/bridging/` package doing BPJS and Dukcapil integrations. We aren't guessing at what a hospital system looks like, we're running one.
- **Model behind a router.** Start with a hosted API for iteration speed. Swap to local open weights (MedGemma 4B or a Qwen-class model) before the demo, to prove the data-residency story works. Never hard-code a model name anywhere except the router config. *(Built: `service/router/`, with two hosted backends so the swap is demonstrated rather than asserted. The local-weights half has not been done. `HostedChatBackend` takes a `base_url` and speaks OpenAI-compatible chat completions, so pointing it at a self-hosted vLLM is a config change, but I have not actually run one, and an untested config change is not a proof of residency.)*
- **The gate is not a model.** Plain Python, a rules table, a formulary table, a drug interaction table. It must be readable by a doctor and diffable in git. If a lawyer or a regulator asks "why did it say that," the answer has to be a file, not a prompt.
- **Postgres for our state, MySQL stays Khanza's.** Don't fight the legacy schema; read from it, write our own. *(Built: `docker-compose.yml` and `db/migrations/`. Optional at runtime, since the store falls back to append-only files and says so. Roughly one facility in twelve doesn't have power around the clock, and a system that won't start without a database is one that often doesn't start.)*


### Do we use an agent framework?

**LangGraph yes. deepagents no.**

> **Status in the prototype: no orchestration library is used, and that is
> deliberate.** `service/graph/runtime.py` defines the durable-runtime contract
> this section argues for (start, checkpoint, interrupt, resume, replay) and
> the encounter workflow exercises all five against an in-memory
> implementation. The signature line really is an interrupt; the audit story
> really is replay. What is absent is a library behind that interface, because
> adding one today buys nothing the in-memory implementation does not already
> provide, and the argument that justifies one (durable execution across days)
> belongs to the between-visit loop, whose patient-facing channel is V1.5.
>
> Durability itself is built, twice: Postgres when a database is reachable and
> three append-only JSONL files when it is not, keeping checkpoints, signatures
> and the outbound queue either way. `python -m tools.store` reads back
> whichever was used, and the clinician surface persists every encounter it
> runs. What is absent is only the orchestration library, not the persistence it
> was wanted for.
>
> The checkpoints are also read rather than merely written. An encounter's
> thread id is derived from its inputs, so a re-run finds the stored result and
> replays it. Fourteen model calls the first time `make live` runs and none
> after that, with a digest of the pack in the id so editing a guideline costs them
> again. That is the difference between a checkpoint and a log entry.
>
> `tests/test_runtime_contract.py` is a conformance suite, and the Postgres
> backend was the first thing run through it, using the same tests rather than a
> suite per backend. That is the claim "swapping the backend is one module's
> work" being discharged rather than asserted; a LangGraph-backed runtime would
> join the same parametrisation. The CI rule confining orchestration imports to
> `/service/graph` stands either way, and is cheap now and impossible to
> retrofit.

Is this an agent? Partly. The intake interview is multi-turn and stateful, and the reasoning step does retrieval and tool calls. But the rest (the gate, coding, FHIR emission) is a pipeline, deliberately. Roughly a third of this system is a graph. Two-thirds is boring deterministic code that gains nothing from one, and that ratio feels about right for something clinical.

**What LangGraph gives us that we'd otherwise build worse:**

- **`interrupt()` *is* our signature line.** The doctor's approval is literally a graph interrupt: pause before an irreversible action, persist the checkpoint, resume from the same `thread_id` once they accept or edit. We were going to hand-roll this, and probably shouldn't.
- **Checkpointers are our offline story.** About 1 in 12 facilities lacks 24-hour power. A checkpoint is a recovery point for interruption, timeout, human handoff and service restart, which are roughly the failure modes a basic-tier hospital actually has.
- **Time-travel replay is our audit story.** When a regulator asks why the system said something, we replay the exact state that produced it. Building that from scratch is months of work.
- **Backend-agnostic.** Swapping a hosted API for self-hosted vLLM is a `base_url` and key change, which is also our model-router requirement and our residency migration path.
- It hit 1.0 in October 2025 with durable execution, streaming, human-in-the-loop and memory stabilised, and it is the framework most often recommended for regulated workflows.

**Two hard boundaries.**

1. **The gate stays out of the graph.** Plain Python, no framework import, testable with nothing else running. If the gate becomes a graph node, sooner or later someone puts a model inside it. It has to stay a file a doctor or a regulator can read.

2. **Self-hosted only. Never LangGraph Platform Cloud or LangSmith SaaS.** GR 28/2024 requires health data to be processed inside Indonesia, and tracing is enabled by default in a lot of setups, which would quietly ship PHI offshore. Self-Hosted Lite (free, up to 1M nodes) is enough for the prototype; BYOC or Self-Hosted Enterprise later. **Add a CI check that fails the build if a LangSmith endpoint is configured.** This is a compliance landmine, not a preference.

The distinction worth internalising: *a framework as a library is fine; a framework as a hosted control plane is a compliance problem.*

**Why not deepagents.** It's built on LangGraph and it's good at what it does: planning, spawning sub-agents, a virtual filesystem the agent manages itself, skills, etc. That's an **open-ended autonomy** harness, and our problem wants closer to the opposite. A consultation isn't really a task to be explored, it's a bounded protocol with a fixed schema, and the sycophancy evidence in [RESEARCH.md](RESEARCH.md) §3 argues for *less* agent freedom in the patient-facing path. Unbounded sub-agent spawning also makes the audit trail non-deterministic, and we have to explain every output. deepagents is the right tool for research and coding agents. Here it would add exactly the freedom we are trying to remove.

**Where the framework goes, and where it doesn't:**

| Component | Framework? |
|---|---|
| Intake interview (multi-turn, stateful) | LangGraph. This is the core use case |
| Reasoning + retrieval | LangGraph node |
| Doctor approval / signature | LangGraph `interrupt()` |
| Follow-up over days and weeks | LangGraph durable execution |
| **The gate** | **Plain Python. No framework.** |
| Fornas + guideline parsing | Plain Python, offline batch |
| FHIR emit, SATUSEHAT client | Plain Python + httpx |
| Coding | Plain Python + one model call |
| Eval harness | pytest |

---

## 2b. Build it as a platform, not a project

The same system is being built for a Japanese client. That is the single most useful engineering constraint we have, because it tells us in advance which lines of code will be thrown away in country three.

The rule: **the clinical core is country-agnostic; everything national lives in a pack.** A pack is data and rules, not code. Swapping the pack swaps the country.

| Pack | Contents | Indonesia |
|---|---|---|
| `terminology` | Code systems, value sets, mappings | ICD-10, ICD-9-CM, LOINC subset |
| `formulary` | Drug list, dosing, interactions, contraindications | Fornas + a hand-curated molecule table |
| `guideline` | Retrievable clinical corpus, versioned | PNPK, PPK |
| `payer` | Coding rules, claim schema, grouper interface | INA-CBG via E-Klaim; iDRG later |
| `interop` | FHIR profiles, auth, submission client | SATUSEHAT, OAuth2, FHIR R4 |
| `language` | Prompts, ASR model, output templates | Bahasa; Javanese and Sundanese later |
| `capability` | Site capability schema and registry | Permenkes 6/2026 service groups |
| `regulatory` | Device threshold, disclosure text, consent copy | Below-device drafting tool; UU PDP consent |

**What this buys us.** Roughly 40% of the engineering effort (the graph, the state model, checkpointing, the interrupt flow, the audit trail, the eval scaffolding) is the slowest and most expensive part to build, and it carries over intact. The 60% that must be rebuilt is mostly content and rules, which is cheaper per hour but needs clinical hires. Deployment three should cost a fraction of deployment two. If it doesn't, we built it wrong.

### The reuse ledger

The same system is being built for a Japanese client, so this is not hypothetical. Component by component, what a second deployment actually costs:

| Component | Verdict | Why |
|---|---|---|
| Orchestration graph, state model, checkpointing, interrupt/approval | **Reuse as-is** | Country-agnostic. The signature line is the same everywhere. |
| Audit trail, versioning, replay, eval harness scaffolding | **Reuse as-is** | Pure infrastructure. Highest-value carry-over after the graph. |
| Deterministic gate *engine* | **Engine yes, rules no** | The nine check types are universal; every threshold, drug and red flag is national. |
| FHIR resource mapping and submission client | **Reuse, reconfigure** | FHIR R4 on both sides. SATUSEHAT auth and profiles differ; the mapping layer survives. |
| Model router | **Reuse, repoint** | Config change. Different models, different hosting, same interface. |
| Clinical corpus: guidelines, formulary | **Rebuild** | PNPK, PPK, Fornas. Nothing Japanese survives. |
| Coding and claims logic | **Rebuild** | DPC/PDPS and INA-CBG are different animals. |
| Evaluation cases, rubrics, gold answers | **Rebuild** | Japanese researchers showed machine translation leaves systematic rubric gaps. |
| Language, ASR, prompts | **Rebuild** | Bahasa plus regional languages. The hardest single rebuild. |
| Drug knowledge base | **Build from nothing** | Japan has commercial pharmacology databases. BPOM is a product registry, not a clinical reference. |
| EMR integration | **Rebuild, and it gets easier** | Khanza is open source. Deeper reach than a Japanese vendor negotiation allows. |
| Offline and low-connectivity operation | **New build** | Japan never needed it. About 1 in 12 Indonesian facilities lacks 24-hour power. |
| ROI model and payer economics | **Rebuild** | Cost-out versus revenue capture. Opposite arguments. |

If a Japanese build already exists, the honest sequencing for week one is *deleting*, not writing: fork the platform, throw away every pack, and rebuild them against Indonesian sources.

**What it costs us.** Discipline. The temptation in an eight-week prototype is to hard-code `"fornas"` and `"BPJS"` into the reasoning layer. Don't. One rule enforces it: *nothing under `/service` may contain a country name, a payer name, a drug name or a guideline name.* That is a grep in CI, and it is cheap now and impossible to retrofit later.

---

## 2c. The capability registry, and why it got more important in June

Gate check 9 (*is this plan executable at this site*) was designed as a clinical requirement. AMIE's one loss to human physicians was on plan practicality and cost-effectiveness, and a plan that prescribes a drug the pharmacy doesn't stock is worse than no plan.

Then the regulation caught up with it. Indonesia's move away from hospital classes A/B/C/D began with PP 28/2024 and Permenkes 11/2025; **Permenkes 6/2026** (enacted 4 June 2026) consolidated 21 hospital regulations and codified it in Article 12. Hospitals are now graded **per service group** on six axes: diagnoses, procedures, staff competency, facilities, infrastructure, equipment. Article 74 requires reporting on all hospital operations into the national health information system. Hospitals have two years from 12 June 2026.

So the registry now has two jobs, and the schema should serve both from day one:

```
site_capability
  site_id
  service_group          # per Permenkes 6/2026, not per hospital
  tier                   # dasar | madya | utama | paripurna
  diagnoses[]            # ICD-10 codes this site can work up
  procedures[]           # ICD-9-CM codes this site can perform
  competencies[]         # practitioner roles present, with SIP validity
  equipment[]            # with working/not-working state and last check
  facilities[]
  hours                  # 24h continuity flags, which the regulation asks for
  evidence_ref[]         # encounter IDs that demonstrate the claim
  as_of
```

`evidence_ref` is the row that matters. The industry association's read of the regulation is that naming a service is no longer sufficient and you have to show it happened. Our encounter data is that proof, already coded. I doubt many people building clinical AI are looking at this, and it's probably the cheapest credibility we'll ever buy with a hospital CFO.

For the prototype: hand-populate three sites, expose it as a read API to the gate, and render one page that renders the capability record as the regulator would want to see it. That page is a demo slide.

---

## 3. Build order

Six phases. Each ends with something demonstrable.

### Phase 0: Environment (week 1)
- Khanza running in Docker with a seeded database.
- Synthea forked and re-weighted for Indonesia, writing patients into Khanza's schema.
- Repo, CI, secrets handling.

**Done when:** you can open Khanza, search a patient, and see a plausible Indonesian history with three prior visits, and a no-op panel has been added to the outpatient consultation form with the round trip timed. That last item is the one that matters, since it's what resolves assumption A1.

**Why Khanza is the first adapter.** It dominates the small-hospital segment, it is open source, it is recognised by the accreditation commission, and its repository already contains a bridging package doing integrations of much this shape, so the pattern isn't novel to that codebase. It's how the codebase already works. Having the source is what makes A1 answerable for most of the estate, and therefore what lets the safety net live inside the consultation form rather than on a second screen. A sequencing advantage, not an architectural commitment: the port in `adapters/base.py` is the commitment, and the fifty-first hospital on a different system needs a new adapter rather than a new product.

### Phase 1: The spine (weeks 2–3)
One encounter travels the whole path with a deliberately stupid model. Hard-code the clinical logic if you have to. The point is the plumbing.

- Read the encounter from Khanza.
- Build the patient state object.
- Call the model.
- Render something in a panel.
- Write a FHIR Encounter and push it to the SATUSEHAT sandbox.

**Done when:** an end-to-end trace exists, even if the output is nonsense.

### Phase 2: Grounding (weeks 3–4)
- Parse the Fornas decree into a structured drug table. Have someone check 200 rows by hand.
- Ingest PNPK and PPK for the chosen pathway; chunk, embed, index.
- Every clinical claim the model makes must carry a citation that resolves, or it gets dropped.

**Done when:** the model cites a real guideline section and you can click through to it.

### Phase 3: The gate (weeks 4–5)
The nine checks, as plain code:

1. Red-flag rules
2. Guideline conformance
3. Drug dose / interaction / allergy
4. Contraindication against this patient's conditions
5. Fornas membership
6. Citation resolves
7. Enough data to answer at all
8. Confidence above the floor, otherwise abstain
9. Executable at this site (is the drug stocked, is the test available)

Build the drug interaction table by hand for the ~60 molecules the pathway actually uses. It's unglamorous and there isn't really a way around it, since there's no Indonesian equivalent of a commercial drug database. BPOM's product registry is marketing authorisations rather than pharmacology.

**Done when:** the 300 broken cases run through and you have a catch rate.

### Phase 4: Features (weeks 5–7)
One complete patient journey, not all thirty features. Pick the vertical slice that shows the whole story:

| Feature | Why it's in the slice |
|---|---|
| Pre-visit history intake | The AI-ness. Nurse-assisted tablet flow. |
| Ambient note → SOAP | The money. |
| ICD-10 coding + claim check | The money, and the bit that pays for everything. |
| Suggested diagnosis | The demo moment. |
| Prescription draft | Where the gate visibly earns its keep. |
| Red-flag traffic light | The Penda proof, in miniature. |
| PRB referral-back draft | `added v6` Deterministic criteria → drafted SRB → same signature line. The Indonesia-only feature, and a demo moment a hospital CFO understands. |

Pathway: **adult hypertension follow-up, alone.** `revised v5` An earlier draft paired it with type 2 diabetes; that is one pathway too many for a first build. Hypertension on its own is protocol-dense, longitudinal, exercises the patient-state layer, and proves the whole architecture without diagnostic entropy. T2DM is V2; combined cardiometabolic management is V3. Fully specified in **[SPEC-V1.md](SPEC-V1.md)**.

> **The prototype now carries a second pathway anyway, and that is not a change of mind.** Type 2 diabetes went into the code as an *architecture test*, to find out whether "the engine is pathway-agnostic" was actually true. It wasn't: the target contract was shaped around blood pressure, refusal routing had learned one pack's rule-numbering convention, and the claim coder produced no primary diagnosis for the second disease. All three are fixed. The pathway has no clinical sign-off, no evaluation set and no adjudicated cases, so **the V1 build order above is unchanged: hypertension alone, done properly.**

**Done when:** you can walk a synthetic patient from waiting room to signed, coded, submitted encounter.

### Phase 5: Eval harness (weeks 7–8)
The scorecard, run on every commit:

| Metric | Bar |
|---|---|
| Red-flag catch rate on planted errors | ≥ 99% |
| Fornas violations | 0 |
| Unresolvable citations | 0 |
| Appropriate abstention when data is missing | ≥ 95% |
| Coding match against gold standard | ≥ 85% |
| Unsafe agreement under 5 turns of patient pressure | < 10% |
| P95 latency per turn | < 3s |

That last-but-one row needs its own small build: a Bahasa Indonesian pressure suite, a few hundred conversations where a simulated patient pushes back ("my sister took this and was fine," "I read online that…", etc.) and we measure whether the model folds. It's probably the most important safety test here, and as far as I can tell nobody else has built one for Indonesia.

**The wider point about evaluation, which is the most under-rated asset in this plan.** Japanese researchers took HealthBench's 5,000 scenarios, machine-translated them, and used an LLM-as-judge to find where the rubrics misalign with Japanese guidelines, health-system structure and cultural norms. GPT-4.1 dropped modestly on rubric mismatch; a Japanese-native open model failed badly on clinical completeness. Japan also has JMedBench and a multi-profession licensing benchmark. **Bahasa Indonesia has none of this.** No adapted clinical benchmark, no medical model leaderboard, no domestic clinical model.

So we cannot buy an answer to "is this safe enough for Indonesia," and neither can anyone else. Two consequences:

- **Reuse the shape, rebuild the content.** Rubric structure, adjudication workflow and scoring pipeline port from any HealthBench-style harness. Every case, every rubric and every gold answer has to be written against Indonesian guidelines and the Indonesian formulary. The Japanese result is the evidence that translating them instead doesn't really work.
- **Build it deliberately, and treat it as an asset rather than a test file.** A few hundred adjudicated Indonesian cases with rubrics is the only instrument in the country capable of telling a hospital, an insurer or the Ministry whether a medical AI is safe here. That's a moat, a regulatory conversation-opener, and something we could publish. Worth budgeting clinical reviewer hours for it explicitly, since it's the one part of the eval harness that can't be generated.

**Done when:** the scorecard runs in CI and a bad commit fails the build.

### Phase 6: Demo (week 8)
- Offline mode: pull the network cable mid-consultation, prove it queues and syncs.
- Local model: run the whole thing with no external API calls, proving residency.
- Two scripted walkthroughs: one where everything is fine and green, one where the gate catches a dangerous prescription.

---

## 4. Repo shape

```
/khanza          docker-compose, schema patches, the injected panel
/datagen         synthea fork, guideline-grounded case generator,
                 broken-case generator
/corpus          fornas parser, guideline ingest, versioned index
/packs
  /id            indonesia: terminology, formulary, guideline, payer,
                 interop, language, capability, regulatory
/service
  /graph         langgraph: intake, reasoning, interrupt/approval
  /state         patient state model + checkpointer config
  /router        model selection + config (never LangSmith cloud)
  /reason        prompts, retrieval, output schemas
  /gate          the nine checks: plain python, no LLM
  /capability    site capability registry + Permenkes 6 evidence view
  /emit          FHIR bundles, SATUSEHAT client, coding
/eval            scorecard, pressure suite, gold sets
/docs            assumption register, decisions log
```

> **Status in the prototype: the shape above is the plan, and the built tree
> differs in four ways worth knowing.** `CODE.md` has the real layout;
> the differences are that `/khanza` and `/corpus` do not exist (no hospital
> system, and guideline content lives in `/packs` rather than a separate
> versioned index), `/service/capability` became `packs/id/capability/sites.yaml`
> because a site registry turned out to be data rather than code, and the tree
> grew `/adapters`, `/db`, `/tests` and `/tools` plus several `/service`
> packages the plan had not anticipated (`intake`, `reconcile`, `present`,
> `followup`, `contracts`, `rules`). `/service/graph` exists and holds the
> durable-runtime contract, but no orchestration library sits behind it, per
> the status note in §2.

Six rules that matter more than they look:

- **`/gate` never imports from `/reason`, and never imports LangGraph.** The gate must be testable with nothing else running.
- **`/service/graph` is the only module that imports the orchestration library.** LangGraph is a good library and still a dependency; behind a thin durable-runtime interface (run, interrupt, resume, replay), swapping it is one module's work instead of a rewrite. Also a grep in CI.
- **Khanza is the first EMR adapter, not the design centre.** Reads and the injected panel go through an adapter interface; hospital #51 on a commercial SIMRS is a new adapter, not a new product. The moment `/service` knows it is talking to Khanza, we have built AI-for-Khanza instead of a clinical platform.
- **Everything in `/corpus` is versioned.** When a guideline updates, we need to know which outputs were produced against which version. This is what makes the system auditable later.
- **Nothing under `/service` names a country, a payer, a drug or a guideline.** All of that lives in `/packs`. Enforced by a grep in CI, because it is free today and impossible later.
- **No LangSmith endpoint may be configured.** Also a CI check. Tracing is on by default in many setups and would ship PHI offshore in breach of GR 28/2024.

---

## 5. Team and time

For a prototype: **2–3 people, 8 weeks.**

- One backend engineer (service, gate, integrations)
- One ML engineer (retrieval, prompts, eval, the pressure suite)
- Part-time clinical input, even a few hours a week from any doctor to sanity-check the generated cases and the gate rules

If a Japanese build already exists, the sequencing changes: see the reuse ledger in §2b. Expect the graph, checkpointing, audit trail, FHIR client and eval scaffolding to carry; expect the corpus, coding, evaluation cases, language layer, drug tables and offline behaviour to be new work. The clinical hire is on the critical path either way, since the packs are what needs a doctor and they're the two-thirds that has to be rebuilt.

The clinical input is the one you cannot skip. A prototype built with no doctor in the loop will look right and be wrong in ways engineers cannot see.

---

## 6. What we deliberately don't build

- **Our own TB imaging model.** WHO has approved six CAD products. We integrate one, or we stub the interface and show where it plugs in.
- **An INA-CBG grouper.** The official grouper assigns severity through the E-Klaim application. We produce accurate codes and feed it.
- **Voice, in v1.** Text intake first. Indonesian medical speech recognition needs fine-tuning data we don't have yet, and it is a whole workstream, not a feature.
- **Multi-hospital anything.** One site, one pathway, done properly.
- **A pretty admin console.** Nobody is evaluating the CRUD screens.

---

## 7. The risk that survives all of this

A prototype on synthetic data proves the machine works. It does not prove the machine helps.

The two failures most likely to kill the real thing (doctors not opening it, and alert fatigue) are invisible in a prototype, because synthetic patients never get annoyed and a scorecard never clicks "dismiss." So the prototype's job is mostly to be good enough to earn a real pilot, and the pilot's job is to answer the questions the prototype can't.

Build it so the data layer swaps out cleanly. Synthetic today, real records the day a hospital says yes, and nothing else in the codebase changes.
