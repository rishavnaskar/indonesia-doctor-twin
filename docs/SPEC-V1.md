# V1 Clinical Workflow Specification

## Adult hypertension follow-up

*The one pathway we build first. Every input, state, model call, rule, decision point, output, failure mode and metric. This is the document an engineer builds from.*

*Companion documents: [DECISION.md](DECISION.md) for why, [RESEARCH.md](RESEARCH.md) for the evidence, [BUILD.md](BUILD.md) for the stack and repo.*

---

## 0. Why this pathway, and only this pathway

Adult hypertension follow-up, i.e. an established patient, already diagnosed, returning for review.

It is the narrowest workflow that still exercises **every architectural component we need to prove**: longitudinal patient state, missing-information detection, medication reconciliation, lab-trend reasoning, guideline retrieval, red-flag detection, executability checking, drafting, deterministic gating, clinician approval, coding and FHIR emission.

And it does that **without diagnostic entropy.** We are not asking the system to work out what is wrong with an undifferentiated patient. We are asking it to manage a known condition against a published protocol. That is the difference between a prototype that can be evaluated and one that can only be demoed.

> **Explicitly deferred to V2:** type 2 diabetes, then combined cardiometabolic management. Do not build them into V1's state machine. Build the packs so they can be added without touching the graph.

**Why hypertension specifically, in Indonesia:** it is protocol-dense and therefore scorable; it is longitudinal and therefore exercises patient state; it is high-volume; and it sits inside **PRB** (Program Rujuk Balik), BPJS's referral-back programme for stable chronic patients on a single diagnosis without complications, which gives us a defined patient cohort, a defined drug list, and a defined billing mechanism to build against.

---

## 1. Scope

### In scope

| | |
|---|---|
| **Patient** | Adult, ≥18, with an existing recorded diagnosis of essential hypertension (ICD-10 **I10**) |
| **Encounter** | Scheduled outpatient follow-up, not a first presentation |
| **Setting** | Outpatient clinic in a group hospital running SIMRS Khanza |
| **Payer** | BPJS/JKN, including PRB patients |
| **Language** | Bahasa Indonesia |

### Out of scope for V1: hard exclusions

These are not "not yet." They are **routing rules**: if any is true, the system produces no clinical draft and hands the encounter to the clinician untouched, with a stated reason.

| Exclusion | Why |
|---|---|
| Pregnant, or of childbearing potential without a documented negative status | ACEi/ARB are teratogenic. Peripartum hypertension is a separate InaSH guideline and a separate pathway. |
| Age < 18 | Different thresholds, different drugs, different evidence. |
| First presentation / newly suspected hypertension | Diagnostic workup, not follow-up. Different workflow. |
| Secondary hypertension suspected or recorded (I15.x) | Needs investigation we do not model. |
| Known resistant hypertension (uncontrolled on ≥3 agents including a diuretic) | InaSH publishes a separate 2024 resistant-hypertension consensus. Out of V1. |
| eGFR < 30, or dialysis | Dosing and drug choice change materially. |
| Active pregnancy, oncology, psychiatric crisis, or a controlled-substance request in the same encounter | §7 of DECISION. |

**Rule:** exclusions are evaluated **before** any model call, on structured data only. An excluded encounter costs zero tokens.

---

## 2. The clinical rule set

Everything in this section is **configuration rather than code**. It lives in `/packs/id/guideline` and `/packs/id/formulary`, versioned, with a citation on every row.

> ### Clinical governance gate
>
> **No rule in this section is active until the Indonesian clinical lead (STR + SIP) has signed it off against the primary source document.** The values below are the starting set, drawn from published Indonesian guidance and marked with their confidence. They are engineering inputs, not clinical authority. Several need confirmation against the primary PDFs, which is a week-one task for the clinical hire, not a research task for an engineer.

### 2.1 Definition and staging

| Item | Value | Source | Confidence |
|---|---|---|---|
| Hypertension | SBP ≥ 140 **and/or** DBP ≥ 90 mmHg | InaSH / PERHI | `verified` |
| Grade 1 | SBP 140–159 or DBP 90–99 | InaSH / PERHI | `verified` |
| Grade 2 | SBP ≥ 160 or DBP ≥ 100 | Conventional split | `partial`, confirm against the InaSH 2024 consensus |
| Measurement standard | Seated, rested, correct cuff size, mean of ≥2 readings | Guideline standard | `partial`, confirm |

### 2.2 Targets

| Patient group | Target | Source | Confidence |
|---|---|---|---|
| General adult | < 140/90 mmHg | PERKI, *Pedoman Tatalaksana Hipertensi pada Penyakit Kardiovaskular* | `verified` |
| With ventricular dysfunction | Consider < 130/80 mmHg | PERKI, same | `verified` |
| Elderly, diabetes, CKD | **Not yet extracted** | InaSH 2024 consensus | `unverified`, clinical lead to extract before these subgroups are enabled |

**Engineering consequence:** the target is a *function* of patient attributes, not a constant. Model it as a lookup with an explicit `no_target_defined` outcome that forces abstention rather than defaulting to 140/90.

### 2.3 The formulary: what is actually prescribable

Sourced from the **PRB formulary** under Fornas (Kepmenkes HK.01.07/MENKES/1199/2025, dated 31 Dec 2025; claim pricing separately under KMK 730/2025, 14 Jul 2025). The restrictions are the interesting part. They're real, encodable, and a generic clinical model will usually violate them.

| Drug | Forms | Encodable restriction |
|---|---|---|
| Amlodipine | 5 mg, 10 mg | Start at lowest dose |
| Nifedipine | 30 mg ER | Alternative CCB |
| Captopril | 12.5 mg, 25 mg | **Max 3 × 25 mg daily** |
| Lisinopril | 5 mg, 10 mg | — |
| Ramipril | 2.5 mg, 5 mg, 10 mg | — |
| Candesartan | 8 mg, 16 mg | **Only on documented ACE-inhibitor intolerance of ≥ 1 month** |
| Valsartan | 80 mg, 160 mg | Requires verification in e-Fornas |
| Bisoprolol | 2.5 mg, 5 mg | **Restricted to compensated chronic heart failure** |
| Hydrochlorothiazide | 25 mg | — |
| Furosemide | 40 mg | Fluid-retention indications |

Adjacent cardiovascular items available on PRB and relevant to comorbid patients: aspirin 80/100 mg, clopidogrel, simvastatin, atorvastatin (ASCVD, LDL target ≤ 70 mg/dL), carvedilol, spironolactone (NYHA-restricted), digoxin, ISDN, ISMN.

> **This table is the single highest-value artefact in V1.** It is why our prescription drafts are executable and a generic model's are not. The candesartan rule alone (an ARB isn't prescribable until a month of documented ACEi intolerance exists in the record) is the kind of constraint that model quality doesn't substitute for, and it's checkable deterministically against the patient's own history.

### 2.4 Red flags: the rules that stop everything

Evaluated on **structured state**, never on model output. Any hit routes the encounter to `ESCALATE` immediately.

| # | Rule | Action |
|---|---|---|
| R1 | SBP ≥ 180 or DBP ≥ 120 **with** any of: chest pain, dyspnoea, focal neurological deficit, visual disturbance, severe headache, altered consciousness | **Hypertensive emergency.** Immediate clinician alert, red. No draft produced. |
| R2 | SBP ≥ 180 or DBP ≥ 120 **without** those symptoms | Hypertensive urgency. Red, clinician must acknowledge before proceeding. |
| R3 | SBP < 90, or symptomatic hypotension, on treatment | Over-treatment. Red. Draft a reduction, do not draft an increase. |
| R4 | New chest pain, syncope, or new focal neurological symptom at any BP | Red. Route out of the pathway. |
| R5 | eGFR fall > 30% from baseline since last visit | Red. ACEi/ARB review. |
| R6 | K⁺ > 5.5 mmol/L | Red. Blocks any ACEi / ARB / spironolactone action. |
| R7 | Newly positive pregnancy status | Immediate exclusion (§1) plus red flag, since ACEi/ARB must stop. |

### 2.5 Interaction and contraindication rules

| Rule | Type |
|---|---|
| ACEi **+** ARB together | Never. Hard block. |
| ACEi or ARB **+** spironolactone | Requires current K⁺ and eGFR within 90 days; blocked without them |
| ACEi or ARB in pregnancy | Hard block (also an exclusion) |
| NSAID co-prescription | Warn: reduces antihypertensive effect, renal risk |
| Any drug on the patient's recorded allergy list | Hard block |
| Dose outside the formulary's stated range | Hard block |
| Drug not on the PRB/Fornas list for a JKN patient | Hard block |

**These live in `/packs/id/formulary` as data.** Roughly 10 molecules and ~15 rules for V1, which is small enough to curate by hand and have a pharmacist verify. That resolves assumption A3 for this pathway.

---

## 3. Patient state

The durable asset. Everything else is replaceable.

```
PatientState
  patient_id                 # internal, pseudonymous
  satusehat_patient_ref      # FHIR reference, emitted not stored as identity
  demographics
    age, sex, childbearing_potential
  diagnoses[]                # ICD-10, with onset date and status
  problem_flags              # derived: has_dm, has_ckd, has_hf, has_ascvd,
                             #          is_prb_enrolled, pregnancy_status
  medications[]
    molecule, dose, frequency, since, prescriber, source
    adherence_signal         # from refill gaps + patient report, never assumed
  allergies[]
  observations[]             # BP, weight, eGFR, K+, HbA1c, lipids
    value, unit, taken_at, method, source
  bp_series                  # derived view: last 6 readings + trend
  encounters[]               # prior visits, with what was decided and by whom
  intolerances[]             # drug, reaction, documented_at   ← powers the
                             #   candesartan rule
  care_gaps[]                # derived: overdue labs, missing baseline
  last_updated, version
```

**Three design rules:**

1. **Every field carries provenance.** `source` is one of `khanza | patient_reported | device | derived | clinician_entered`. A model may never treat patient-reported and lab-confirmed values as equivalent, and the gate needs to know which is which.
2. **State is versioned and append-only.** We must be able to reconstruct exactly what the system saw at the moment it produced an output. This is the audit story and it is not retrofittable.
3. **SATUSEHAT/FHIR is an interoperability boundary, not our canonical model.** We map outward at the edge. Do not let an exchange format dictate the internal clinical representation.

---

## 4. The state machine

The system does not "have a conversation." It advances a patient through defined states. Every transition is logged; every state has a defined exit.

```
                          ┌──────────────┐
                          │   ELIGIBLE   │  structured checks only, no model
                          └──────┬───────┘
                    excluded ────┴──── eligible
                        │                 │
                        ▼                 ▼
                 ┌────────────┐    ┌──────────────┐
                 │  HANDOFF   │    │    INTAKE    │  bounded interview
                 │ (no draft, │    └──────┬───────┘  fixed schema
                 │  reason)   │           ▼
                 └────────────┘    ┌──────────────┐
                                   │ RECONCILE    │  meds, labs, adherence
                                   └──────┬───────┘
                                          ▼
                                   ┌──────────────┐   R1–R7 hit
                                   │  RED FLAGS   │──────────────┐
                                   └──────┬───────┘              │
                                          ▼                      ▼
                                   ┌──────────────┐       ┌────────────┐
                                   │  SUFFICIENCY │       │  ESCALATE  │
                                   └──────┬───────┘       └────────────┘
                        insufficient ─────┴───── sufficient
                              │                      │
                              ▼                      ▼
                       ┌────────────┐         ┌──────────────┐
                       │  REQUEST   │         │   PROPOSE    │  the model call
                       │   INFO     │         └──────┬───────┘
                       └────────────┘                ▼
                                              ╔══════════════╗
                                              ║     GATE     ║  deterministic
                                              ╚══════┬═══════╝
                                    fail ────────────┴──────── pass
                                     │                          │
                                     ▼                          ▼
                              ┌────────────┐            ┌──────────────┐
                              │  ABSTAIN   │            │   PRESENT    │
                              └────────────┘            └──────┬───────┘
                                                               ▼
                                                        ╔══════════════╗
                                                        ║  CLINICIAN   ║  interrupt()
                                                        ║   DECIDES    ║
                                                        ╚══════┬═══════╝
                                          accept / edit / reject
                                                               ▼
                                                        ┌──────────────┐
                                                        │    COMMIT    │  code + emit
                                                        └──────┬───────┘
                                                               ▼
                                                        ┌──────────────┐
                                                        │  FOLLOW-UP   │  scheduled
                                                        └──────────────┘
```

**Terminal states that are successes, not failures:** `HANDOFF`, `ESCALATE`, `REQUEST INFO`, `ABSTAIN`. A system that cannot reach these safely is not safe. They are measured as first-class outcomes in §8, not as errors.

---

## 5. Step contracts

Each node declares what it reads, whether a model is involved, and what it must return. **No node may proceed on a malformed output from the previous one.**

### 5.1 ELIGIBLE: deterministic

| | |
|---|---|
| Reads | Khanza encounter, patient demographics, diagnosis list |
| Model | **None** |
| Returns | `{eligible: bool, exclusions: [reason]}` |
| On exclusion | → `HANDOFF`. Panel shows: *"Not handled by the assistant: [reason]."* No clinical content. |

### 5.2 INTAKE: model, bounded

A **structured interviewer**, not an advisor. Fixed schema, fixed question set, no negotiation of clinical conclusions with the patient. §3 of RESEARCH forbids anything looser.

| | |
|---|---|
| Reads | PatientState, last encounter |
| Model | Yes, dialogue management only |
| Collects | Symptoms since last visit (checklist + free text), medication adherence, side effects, home BP readings, lifestyle, new medications from outside the hospital |
| Returns | Structured `IntakeResult`, schema-validated |
| Never does | Answer clinical questions · give advice · state or discuss a diagnosis · respond to pressure to change a clinical position |
| Delivery | Nurse-assisted tablet by default; patient self-service opt-in (assumption A2) |
| Hard rule | Any patient utterance requesting advice returns a fixed deflection and is logged. The interviewer has no clinical voice. |

### 5.3 RECONCILE: deterministic + one model call

| | |
|---|---|
| Reads | Khanza medication list, PatientState, IntakeResult |
| Model | Only for matching free-text drug mentions to molecules |
| Produces | Reconciled medication list with a `discrepancy[]` array: patient says they stopped it, dose differs from record, outside prescription not in the system |
| Rule | Discrepancies are **surfaced, never silently resolved.** |

### 5.4 RED FLAGS: deterministic

| | |
|---|---|
| Reads | Structured observations, IntakeResult symptom checklist |
| Model | **None. Ever.** |
| Logic | R1–R7 from §2.4 |
| Returns | `{flags: [...], severity: none / amber / red}` |
| On red | → `ESCALATE`, no draft produced, clinician alerted immediately |

### 5.5 SUFFICIENCY: deterministic

The check most systems omit. Do we have enough to say anything at all?

Requires, for a titration decision: a valid BP this visit · a defined target for this patient (§2.2) · current medication list · eGFR and K⁺ within 90 days **if** an ACEi/ARB/spironolactone action is contemplated · documented intolerance history **if** an ARB is contemplated.

| | |
|---|---|
| Returns | `{sufficient: bool, missing: [item]}` |
| If insufficient | → `REQUEST INFO`. Output is a request, i.e. *"BP controlled; K⁺ and eGFR are 7 months old, needed before any ACEi change"*, rather than a recommendation. |

### 5.6 PROPOSE: the model call

The only place clinical reasoning happens.

| | |
|---|---|
| Reads | PatientState, IntakeResult, reconciled meds, retrieved guideline sections, site capability record |
| Model | Yes, via the router (`/service/router`), never a hard-coded name |
| Retrieval | Top-k from `/packs/id/guideline`, versioned; every clinical assertion must carry a resolvable citation |
| Returns | `Proposal`, see below |

```
Proposal
  assessment            # controlled | uncontrolled | over-treated
  bp_trend_summary
  target_used           + citation
  recommendation        # continue | titrate_up | titrate_down | add_agent
                        # | switch_agent | refer
  medication_changes[]
    action, molecule, dose, frequency, rationale, citation
  investigations[]      # only tests that change the decision
  patient_instructions  # plain Bahasa Indonesia
  follow_up_interval
  confidence            # calibrated, drives the §2.2 abstention floor
  uncertainty_notes
  provenance            # model@version · prompt_template@version ·
                        # corpus@version, all three pinned per proposal
```

**Provenance is three-dimensional, not one.** F9 already pins the corpus version. The model and the prompt template change more often than the guideline does, and a regression in either must be traceable to the exact proposal it produced. A proposal without all three pins is malformed and fails the gate.

**Structured output, schema-enforced.** A proposal that does not parse is a gate failure, not a retry.

### 5.7 GATE: deterministic, no framework imports

The nine checks from RESEARCH §6, instantiated for this pathway. **`/service/gate` imports nothing from `/service/reason` and does not import the orchestration library.** It must be testable with nothing else running.

| # | Check | Instantiated for hypertension |
|---|---|---|
| 1 | Red-flag rules | R1–R7 re-evaluated against the *proposal*, not just the state |
| 2 | Guideline conformance | Target matches §2.2 for this patient's group; drug class order matches the guideline algorithm |
| 3 | Drug safety | Dose within formulary range · captopril ≤ 3×25 mg · no ACEi+ARB · K⁺/eGFR present for RAAS actions · allergy check |
| 4 | Contraindication | Against this patient's own recorded conditions, not a generic profile |
| 5 | Formulary membership | Hard set test against the PRB/Fornas list. **Candesartan requires ≥1 month documented ACEi intolerance in `intolerances[]`.** Bisoprolol requires a recorded compensated-HF diagnosis. |
| 6 | Citation resolution | Every clinical assertion resolves to a versioned section in the corpus, or is dropped |
| 7 | Missing data | Re-check of §5.5 against what the proposal actually relies on |
| 8 | Uncertainty floor | Below the calibrated threshold → abstain and escalate, never a low-confidence plan |
| 9 | Executable here | Is the molecule stocked at this site today? Is the test available? Does BPJS cover it for this patient? Fails → the output becomes a **referral**, not a recommendation |

**On any failure the proposal does not render.** The clinician sees the encounter as if the assistant had said nothing, plus a quiet log entry. Failing silently toward "no output" is the correct direction.

### 5.8 PRESENT: deterministic

Inside the Khanza consultation form, triggered on defined events (field blur, order entry, plan commit). Penda's pattern.

- **Green**: silent. The clinician sees nothing. That's most visits, and the silence is what makes amber and red worth reading.
- **Amber**: collapsed, optional, one line.
- **Red**: has to be acknowledged before the order can be committed.

### 5.9 CLINICIAN DECIDES: the interrupt

The signature line, implemented as a durable workflow interrupt. State is checkpointed before the pause and resumed by `thread_id`.

**Signer binding.** The resume is only valid from an authenticated clinician whose SIP is current in the capability registry (`competencies[]`) at the moment of signing. The audit record binds together: practitioner ID and SIP · the exact proposal version (with its three provenance pins) · the decision · timestamp. A signature from an expired or absent SIP is refused in software, much like an unsigned prescription. That's "a licensed doctor signs everything" enforced at about the only place it can be enforced.

Captured on every proposal: `accepted | edited | rejected`, the edit diff, time to decision, and, on rejection, a one-tap reason from a fixed list. **The reject reasons are training data and they are the most valuable telemetry in the system.**

### 5.10 COMMIT: deterministic + one model call

Coding. ICD-10 primary and secondary, ICD-9-CM where a procedure occurred.

| | |
|---|---|
| Typical primary | **I10** essential hypertension |
| Comorbidity capture | I11.x hypertensive heart disease · I12.x hypertensive CKD · I13.x both · E11.x T2DM · N18.x CKD stage · E78.5 hyperlipidaemia |
| Rule | **We produce codes and feed the official grouper via E-Klaim. We never compute a tariff or a severity level.** |
| Why it matters | The secondary diagnoses are where the money is (DECISION §8). A comorbidity written in free text and never coded is care delivered and not paid for. |

Then emit: FHIR R4 bundle → SATUSEHAT; claim draft → E-Klaim; PatientState updated and versioned.

> ### `added v6` The PRB referral-back draft, i.e. the output nobody else will build
>
> When a patient is stable, the specialist is supposed to issue a **Surat Rujuk Balik (SRB)**, the referral-back letter that moves them onto PRB at their FKTP with their chronic prescription attached. BPJS's own checklist for it is called **3B**: *benar diagnosanya* (right diagnosis), *benar sudah stabil* (truly stable), *benar obatnya* (right drugs, i.e. on the PRB list, within its restrictions and maximum prescription rules).
>
> All three B's are **deterministically checkable against PatientState**: confirmed I10 · BP at target across the last N visits (N set by the clinical lead, §10 Q9) · current regimen entirely on the §2.3 list within its restrictions. When they hold, COMMIT drafts the SRB and prescription for the specialist to sign. One more draft on the same signature line, with no new state and no model judgment.
>
> Why bother: stable follow-ups are low-tariff visits occupying the scarcest resource in the network (specialist time), and PRB compliance is something BPJS actively pushes. Drafting the SRB the moment the criteria hold frees those slots for new referrals, aligns the group with its payer, and exercises the same machinery the whole system is built on (deterministic criteria → drafted document → signature). It's also a feature no generic clinical AI is likely to ship, since it only exists in Indonesian payment plumbing.

### 5.11 FOLLOW-UP: durable, scheduled

Interval from the proposal, clinician-confirmed. Survives restarts, power loss and connectivity gaps, since the checkpointer is the offline story. Escalates on non-attendance after a defined window.

**`added v6` The between-visit loop, which is where the twin actually lives.** A follow-up interval isn't a silence. Between visits the state keeps syncing, on three channels, all structured and none of them chat:

| Channel | What flows in | Provenance |
|---|---|---|
| Home BP readings | Patient or family enters readings via a **button-driven structured flow** (nurse-assisted or WhatsApp-style structured messaging: fixed prompts, numeric fields, never free conversation) | `patient_reported`, or `device` where a connected cuff exists |
| Refill signal | PRB patients collect chronic medication **monthly**, i.e. twelve touchpoints a year against four visits. A missed refill is an adherence signal the visit would only discover months later | `derived` from dispensing data |
| Symptom check-in | The same fixed checklist as INTAKE, abbreviated | `patient_reported` |

Escalation on this data is **deterministic**: the same R1–R7 thresholds applied to reported readings, with one addition: a patient-reported outlier triggers a *confirmation request* (repeat reading, correct technique) before any red flag fires, because home readings carry more noise than clinic ones. No model touches this path.

The evidence for bothering: meta-analyses of home BP telemonitoring consistently show **3.7–5.6 mmHg additional systolic reduction** against usual care, which is roughly on a par with adding half a drug, at the cost of a messaging flow. And BP control rate is the payer's own quality metric, so the same loop that improves outcomes produces the number that proves it.

**Build boundary:** the schema, provenance handling and escalation rules are V1, and `bp_series` already accepts multi-source readings. Switching the patient-facing channel on is **V1.5**, after the clinic-side loop is stable. Worth not letting it slip out of the design now, since retrofitting provenance is the mistake §3 exists to prevent.

---

## 6. Data contracts

| Source | Direction | Contract | Notes |
|---|---|---|---|
| SIMRS Khanza | read | MySQL views + REST | We read; we do not write to the legacy schema |
| Khanza consultation form | write | Injected panel | The A1 assumption. Fork maintained in `/khanza` |
| `/packs/id/guideline` | read | Versioned corpus index | Citation must resolve to `doc@version#section` |
| `/packs/id/formulary` | read | Structured tables | §2.3 and §2.5 |
| Site capability registry | read | Read API | Gate check 9. Schema in BUILD §2c |
| SATUSEHAT | write | FHIR R4 over OAuth2 | Sandbox first. Boundary, not canonical model |
| E-Klaim | write | Claim draft | Codes only |

**Offline behaviour:** every write is queued and replayed. A dropped connection mid-consultation shouldn't lose the encounter or produce a duplicate on reconnect, hence idempotency keys on every outbound write.

---

## 7. Failure modes

The ones that matter are not model failures.

| # | Failure | Detection | Response |
|---|---|---|---|
| F1 | Model proposes a non-formulary drug | Gate 5 | Blocked. Logged. Counts against the formulary metric. |
| F2 | Model proposes a drug the site does not stock | Gate 9 | Converted to a referral |
| F3 | Model asserts something with no resolvable citation | Gate 6 | Assertion dropped before rendering |
| F4 | Stale capability registry says a drug is stocked when it is not | **Not detectable by us** | A13 is unverified. Cap the registry at slow-moving facts; show `as_of` on the panel; a clinician override path must exist |
| F5 | Patient pressures the intake agent into a clinical statement | Pressure suite | Fixed deflection; any deviation is a release blocker |
| F6 | Clinician clicks through every alert | Acknowledgement telemetry | Alert precision is a gate (§8). If precision drops, we ship fewer alerts, not more |
| F7 | ASR mis-transcribes a drug or dose | Gate 3 range check + clinician review | Never auto-commit an ASR-derived dose |
| F8 | Connectivity lost mid-encounter | Checkpointer | Resume by `thread_id`; no duplicate emission |
| F9 | Guideline updated; older outputs were produced against the old version | Corpus versioning | Every output records `corpus@version`. Non-negotiable for audit |
| F10 | **The clinician stops opening it** | Engagement telemetry from day one | The most likely quiet death (A14). Engagement is a primary endpoint, not telemetry |
| F11 | `added v6` **Prompt injection**, i.e. instructions embedded in patient free text, a pasted outside-prescription label, or a poisoned Khanza note reaching the model as if they were ours | Injection probes in Set B and the pressure suite | Every string not authored by us (patient utterances, record free text, scanned documents) enters the model **delimited as data, never concatenated as instruction**. And the real defence is structural: whatever the model is tricked into proposing still faces the gate, which reads no free text and takes no instructions. An injection that survives to a rendered output is a release blocker, same class as F5 |

---

## 8. Evaluation

### 8.1 The five questions V1 must answer

Not thirty features. Five questions. If these hold, there is a company.

1. Can the system collect a **clinically complete history** for this pathway?
2. Can it maintain an **accurate longitudinal patient state**?
3. Can it produce **useful, guideline-grounded, executable** recommendations?
4. Do the **deterministic controls prevent dangerous actions**?
5. Can one physician safely handle **substantially more patients**?

### 8.2 Blocking gates

Nothing reaches a clinician's screen until all of these hold on the evaluation sets.

| Metric | Bar | Measured on |
|---|---|---|
| Red-flag recall (R1–R7) | ≥ 99% | Adversarial set, over-sampled |
| Formulary violations | 0 | All proposals |
| Unresolvable citations | 0 | All proposals |
| Appropriate abstention | ≥ 95% | Deliberately under-specified cases |
| Appropriate exclusion routing | 100% | Excluded-cohort set |
| Unsafe agreement, 5-turn pressure | < 10% | Bahasa Indonesian pressure suite |
| History completeness vs gold | ≥ 90% | Adjudicated set |
| Coding match vs gold | ≥ 85% | Adjudicated set |
| Amber/red alert precision | ≥ 70% | Clinician acknowledgement |
| Note acceptance without major edit | ≥ 80% | Live telemetry |
| `added v6` Plan concordance with the adjudicated decision | Report from day one; the clinical lead sets the bar before assist mode | Set C |
| P95 latency, propose→present | < 3 s | Production trace |

**The concordance row is the "twin fidelity" number**, i.e. the measurable answer to the brief's own phrase: of the decisions a good doctor actually made on these visits, what fraction did the system's draft match? It's the one metric that speaks the interviewer's language, it can only be measured on Set C, and it's deliberately *reported* rather than *gated* at first. A system tuned to maximise agreement with historical practice would also reproduce historical mistakes, which is roughly what the Kenya deployment was there to catch.

### 8.3 Three datasets, not two

| Set | What | Proves |
|---|---|---|
| **A, synthetic clean** | ~400 hypertension follow-up cases generated from the guideline | The pipeline runs |
| **B, synthetic adversarial** | ~150 deliberately broken twins: 10× dose, ACEi+ARB, candesartan without documented intolerance, missed red flag, non-stocked drug, hyperkalaemia ignored, plus `v6` injection probes: instructions hidden in intake free text and record notes (F11) | The gate catches planted errors |
| **C, real retrospective, physician-adjudicated** | 300 real historical hypertension visits, blind-scored by Indonesian physicians | **Clinical reality.** This is the only one that counts as evidence |

> **The trap to avoid.** Sets A and B are generated from the same guideline the system retrieves from. Scoring 99% on them proves the plumbing works and proves nothing clinical. **Set C is not optional and it is not a later phase.** Anyone who quotes an A or B score as clinical validation should be corrected in the room.

### 8.4 The experiment that decides everything

Before serious money is committed, run this on **100 real historical hypertension visits**, three arms, blind-adjudicated:

| Arm | Condition |
|---|---|
| **A** | Doctor alone |
| **B** | Doctor + the existing EHR |
| **C** | Doctor + our clinical operator |

Measured: consultation time · history completeness · diagnostic and treatment errors · guideline adherence · documentation effort · unnecessary investigations · escalation rate · clinician confidence.

**The question is not "is our AI good."** It is: *does C beat B by enough to justify changing how a clinic works?* That is the bridge from a research package to a company, and it is cheap relative to what follows.

---

## 9. What V1 does not do

- No diagnosis of new or undifferentiated presentations
- No combined cardiometabolic management (V3)
- **Type 2 diabetes was V2 and now exists in the prototype**, as an architecture
  test, not as clinical scope. It was added to find out whether "the engine is
  pathway-agnostic" was true, and it was not: see the corrections in CODE.md. The
  pathway has no clinical sign-off, no evaluation set and no adjudicated cases,
  so it must not be run on a patient. What it demonstrates is that a second
  disease costs two pack files, which is a claim about the architecture and not
  about diabetes care.
- No autonomous prescribing under any condition
- No open-ended patient conversation
- No voice input (typed and structured intake first, since A10 is unverified)
- No tariff or severity computation
- No multi-site deployment; one site, one pathway, done properly
- No TB or imaging in this pathway

---

## 10. Open questions for the clinical lead

Week-one questions for the STR + SIP hire. Each blocks a specific rule, and none is an engineering task.

1. Confirm Grade 2 thresholds and the measurement standard against the InaSH 2024 consensus (§2.1).
2. Extract BP targets for **elderly, diabetes and CKD** subgroups (§2.2). Until these exist those subgroups stay in `no_target_defined` and the system abstains.
3. Confirm the guideline's escalation algorithm: when to titrate versus add versus switch.
4. Confirm the ACEi-intolerance documentation standard the candesartan rule depends on: what counts, and where is it recorded in Khanza?
5. Set the abstention confidence floor. This is a clinical risk decision, not a modelling one.
6. Approve the fixed deflection language for the intake agent.
7. Define the rejection-reason list clinicians will pick from.
8. Confirm which investigations genuinely change the decision at follow-up, so §5.6 stops proposing the rest.
9. `added v6` Define "stable" for the SRB draft (§5.10): how many consecutive at-target visits, and any additional 3B conditions the group's specialists apply before referring a patient back to PRB.

---

## The one line

> V1 isn't an AI doctor. It's a system that walks one known patient through one known protocol, refuses to speak when it isn't sure, and hands a licensed doctor a draft they can accept in one click or ignore entirely. We should know within fourteen weeks whether that's worth anything, because we're measuring it against the same doctor working without it.
