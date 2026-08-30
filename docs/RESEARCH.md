# The 67% Doctor

*Internal research memo · Office of the CTO · evidence current to 29 August 2026 · v6*

A deep read of what clinical AI can actually do as of August 2026, what it demonstrably cannot, and an architecture for a 50-hospital Indonesian network. The testable claim is that **a large majority of a doctor's task-minutes are addressable today** — while 100% of the accountability stays with a licensed human. The title names the brief's target, not a measured result: the real figure is what the pilot exists to establish.

| | |
|---|---|
| **0.47** | Doctors per 1,000 people in Indonesia — under half the WHO reference of 1.0 |
| **−16%** | Diagnostic errors in the largest real-world deployment study — Kenya, 39,849 visits, quality-improvement design |
| **50.5%** | Rate at which medical LLMs capitulate to a wrong patient premise under 5 turns of pressure |
| **~4 in 5** | Indonesian general hospitals sit in the bottom two capability tiers — the real deployment target |

> **How to read this**
>
> **This is reference material, not a document to read end to end.** It exists so that every claim in [DECISION.md](DECISION.md) can be traced, checked or attacked. Use the contents list to jump to what you want to test. If you want the argument rather than the workings, read [DECISION.md](DECISION.md) — about twelve minutes.
>
> Every claim here is graded. `verified` means confirmed against a primary or peer-reviewed source; `partial` means the evidence is indirect or contested; `vendor` means company-reported and unverified. The [corrections log](#corrections) at the end lists everything that changed between drafts and why — including the things I got wrong.

---
---

## Contents

1. [§0 The asset](#s0)
2. [§1 The reframe](#s1)
3. [§2 What is actually shipping](#s2)
4. [§3 What breaks](#s3)
5. [§4 Indonesia's constraints](#s4)
6. [§4a The Japan precedent](#s4a)
7. [§5 Where the 67% comes from](#s5)
8. [§6 Reference architecture](#s6)
9. [§6a Assumption register](#s6a)
10. [§7 The MVP](#s7)
11. [§8 Autonomy ladder](#s8)
12. [§9 Evaluation gates](#s9)
13. [§10 Unit economics](#s10)
14. [§10a Value creation](#s10a)
15. [§11 Parameters I set](#s11)
16. [§— Corrections log](#corrections)
17. [§— Sources](#src)

<a id="s0"></a>

**§0 — THE ASSET**

## Specifying the network, since nobody handed me one

A plan that says "assume 50 hospitals" is not a plan. Indonesia's hospital sector is well documented publicly, so rather than wait for parameters I have set them — every one traceable to a named source, every one falsifiable the day real data arrives.

The archetype is a listed, multi-province Indonesian hospital group. **Hermina** is the closest real comparator at 52 hospitals across 63 cities in 17 provinces as of December 2024, with trailing revenue around USD 436M. **Siloam** is the profitability benchmark at 41 hospitals, ~USD 724M revenue, roughly 4,000 beds, 65% occupancy and a 24% EBITDA margin. **Muhammadiyah** shows the other shape a 50-hospital network can take — 97 hospitals and 214 clinics serving ~12M patients a year, mostly small and faith-based.

| Parameter | Value I'm using | Basis |
|---|---|---|
| Hospitals | 50 | Given in the brief. Hermina's 52 is the live comparator. |
| Capability mix | ~6 upper-tier · ~26 mid-tier · ~18 basic (formerly B / C / D) | `revised v3` Modelled from the national distribution (old classes C and D were ~81–83% of general hospitals), skewed one notch up because a commercial group outperforms the national tail. Permenkes 6/2026 replaced these single labels with per-service-group tiers, so from mid-2026 a site is *madya* in one service and *dasar* in another. That makes the mix harder to state in one row — and it is exactly why the capability registry in §6 is now a compliance artefact as well as a clinical one. |
| Geography | 15–17 provinces, majority outside Jakarta | Hermina operates in 17 provinces / 63 cities. The brief's premise — "they don't have good doctors" — only makes sense off Java. |
| Revenue | ~USD 420M | Hermina TTM ~USD 416–436M. |
| EBITDA margin | 20%, so ~USD 84M | Siloam reports 24%; a C/D-weighted group sits below the sector leader. |
| BPJS share of revenue | 55% | `modelled` Volume-driven Indonesian groups are heavily JKN-exposed. This is the assumption with the largest effect on §10a — it needs replacing first. |
| Outpatient volume | ~3.0M visits/year | 50 × ~200 visits/day × ~300 operating days. |
| SIMRS estate | Mixed: SIMRS Khanza at most C/D sites, one or two commercial vendors at class B | See below — this is the finding that unblocks the architecture. |
| Connectivity | ~1 site in 5 unreliable; ~1 in 12 without 24-hour power | Measured at puskesmas level (§6a A8); hospitals are better but the class D tail overlaps. |

*Every figure is either sourced or explicitly modelled. Where I modelled, the basis is stated so the number can be replaced rather than argued with.*

### The SIMRS question answers itself

I asked for vendor names because §6a A1 — can we render a traffic light inside the consultation form — was the assumption most likely to kill the design. It turns out the Indonesian market answers this without a client call.

> **SIMRS Khanza**
>
> Indonesia's dominant hospital information system in the class C/D segment is **free and open source**. SIMRS Khanza is a Java client–server application over PHP/MySQL, published on GitHub, recognised by the hospital accreditation commission (KARS), and supported by a foundation (YASKI, established 2017). Adoption estimates range from 500 to over 1,500 hospitals depending on source — either way, the largest installed base in the country.
>
> Its repository already contains a `src/bridging/` package with working integrations to BPJS PCare, Siranap bed reporting and Dukcapil identity checks. The pattern we need is not novel to this codebase; it is how the codebase already works.

Two consequences. First, **A1 is resolved for the majority of the estate**: where a site runs Khanza we have the source and can implement the in-form safety net properly, on real events, rather than settling for a second-screen companion. Second, the commercial segment has a route too — Indonesian SIMRS procurement commonly uses KSO arrangements in which *source code becomes hospital property*, which is precisely the contractual hook a portfolio owner can pull.

That reframes the integration problem from "will a vendor cooperate" to "how many distinct forks do we maintain." The answer for the MVP is one, and it should be Khanza.

**What I could not resolve without the asset**

- The actual BPJS revenue share, which drives most of §10a.
- Whether the group employs its clinicians or contracts them — the Penda lesson, and the difference between mandating a workflow and hoping for adoption.
- Per-site stock lists, which seed the hospital capability registry.
- Current coding accuracy and pending-claim rate, which set the baseline the whole value case is measured against.

Each is a number to be replaced, not a blocker. The plan is built so that replacing them changes the size of the prize, not the shape of the build.

---

<a id="s1"></a>

**§1 — THE REFRAME**

## "Digital twin of a doctor" is an ambiguous specification

Not because the target is wrong — 60–70% of what a doctor does is the right ambition and it is achievable. Because the phrase admits two readings that need almost the same software and produce completely different companies, and picking the wrong one costs a year.

A doctor is not a function that maps symptoms to prescriptions. A doctor is a *licensed, insurable, accountable legal person* who performs roughly eleven distinct tasks inside a consultation, only some of which involve reasoning. When you say "60–70% of what a real doctor does," there are two very different things you could mean:

- **60–70% of the clinical judgment** — i.e. the system decides, and a human spot-checks. This is what "digital twin" implies. `revised v2` Indonesia has no AI-specific health legislation, so this is not *explicitly* outlawed. But UU 17/2023 vests the delivery of medical services in practitioners holding STR and SIP, and nothing in GR 28/2024 creates a route for a system to hold that accountability itself. Treat it as regulatorily unresolved, uninsurable today, and unsupported by the evidence — not as settled law. We need Indonesian regulatory counsel to convert this from a working assumption into a position.
- **60–70% of the task-minutes** — the system does the history, the drafting, the retrieval, the checking, the documentation, the coding, the follow-up; the doctor does the judging and signs. This is achievable now, is where every credible deployment in the world sits, and it produces the same throughput outcome you actually want.

These two framings produce almost identical productivity numbers and completely different companies. The second ships in a quarter; the first is a research programme with a regulatory dead end at the far side.

> **A specific warning about the "twin" framing**
>
> There is a live product category of literal physician digital twins — voice-cloned, name-attached personas of a named doctor. 9verse's twin of Dr. Mansoor Habib in the UAE is one; Personal.ai markets another, pitched as an AI "trained to comprehensively embody an individual doctor's medical data, decision-making frameworks, accumulated clinical experience," reachable by patients via messaging and a dedicated phone number.
>
> Personal.ai's page is worth reading closely, because it shows exactly where this category breaks. It disclaims diagnosis and prescribing — but it offers to help patients "understand test results" and "run possible treatment plans," in an open-ended conversation, under a real doctor's name. That is the precise combination §3 says is unsafe: multi-turn, patient-facing, clinically consequential dialogue, where unsafe agreement runs above 50% by turn five — except here the patient believes they are talking to *their physician*, so the authority that would normally cause them to check with a human is the very thing being simulated. The page carries no named deployment, no clinical validation, no regulatory statement, and no pricing.
>
> Cloning a doctor's voice and likeness adds *zero* clinical capability and imports impersonation risk, consent complexity, and — under a forthcoming Indonesian AI ethics Perpres — probable classification as high-risk. The medical literature has already started naming this problem ("AI impostors"). Recommend we never personify the system as a specific human clinician. Give it a product name, an obviously-synthetic voice, and a disclosure on every turn. Note that this is a constraint on the *interface*, not on the technique: modelling a named doctor's decision policy behind the scenes (§8, L4+) is a legitimate and valuable thing to do. Wearing their face is not.

So the working specification I'd propose to the board is: **a supervised clinical agent that absorbs 60–70% of the work of a consultation and returns a signed, coded, SATUSEHAT-compliant encounter — with a licensed Indonesian doctor as the sole signer and a measurable reduction in diagnostic and treatment error as the primary endpoint.**

---

<a id="s2"></a>

**§2 — STATE OF THE ART**

## What is actually shipping in August 2026

Two years ago this was all benchmark scores. It isn't any more — there are now real deployments with real denominators. Here is everything that matters, with the evidence grade attached, because the gap between the peer-reviewed rows and the vendor rows is enormous.

| System | Setting & scale | Result that matters | Grade |
|---|---|---|---|
| AMIE, real-world Google Research | Beth Israel Deaconess, ambulatory primary care. 100 patients did a pre-visit text interview with AMIE; 98 attended the visit. Preregistered, IRB-approved. | AMIE's differential contained the final diagnosis in 90% of cases; 75% top-3 accuracy. Blinded raters scored its diagnostic quality similar to the PCPs'. **Zero safety stops** were triggered by the human supervisors. But PCPs beat AMIE on the *practicality and cost-effectiveness* of management plans. | `peer-reviewed` |
| AMIE, disease management | Simulated longitudinal consultations with trained patient actors, graded by specialists. *Nature*, 17 June 2026. | Matched PCPs on overall management reasoning and scored *higher* on plan preciseness and guideline alignment when given long-context access to NICE/BMJ guidelines and a drug formulary. Introduced RxQA, a 600-item formulary-reasoning benchmark. | `peer-reviewed` |
| AMIE (Video) Google Research, 11 Aug 2026 | `revised v2 — added` Randomised OSCE: 100 scenarios across five body systems, 300 consultations, 15 trained patient actors, 10 board-certified PCP comparators, 20 physician evaluators. | Real-time *video* consultation built from three parallel agents — a patient-facing talker, a background planner doing the clinical reasoning, and a perception agent reading audio-visual cues. Rated comparable to PCPs on history-taking, diagnostic accuracy, management and communication, and **significantly better than PCPs at eliciting physical signs** and guiding patients through virtual examination manoeuvres. Simulated actors, not real patients. | `preprint` |
| AI Consult Penda Health × OpenAI | 15 primary care clinics, Nairobi. 39,849 visits Jan–Apr 2025 (20,859 with AI, 18,990 without). 5,666 visits independently adjudicated by physicians. | **−16% relative reduction in diagnostic errors, −13% in treatment errors**, with outcomes rated by independent physicians. Extrapolated by the authors to ~22,000 diagnostic and ~29,000 treatment errors averted annually at Penda's scale. Every clinician said it improved their care; 75% said "substantially." No harm attributed. `revised v2` The authors describe this as a *quality-improvement study*, not a randomised trial — clinicians were compared with and without access, not randomised. Still the single most relevant result we have; just not RCT evidence. | `preprint` |
| eSanjeevani AI-CDSS Govt of India | National teleconsultation platform. 64M historical consults mined to build a SNOMED-aligned symptom form; 115 symptoms at launch, 300 by 2025. | Deployed across a service that has now handled 282M+ consultations. Improved structured data capture and triage. Proof that a national-scale LMIC CDSS rollout is operationally possible. | `preprint` |
| Dr Hua Synyi AI × Almoosa | Al-Ahsa, Saudi Arabia. First clinic where an AI runs the consultation end-to-end. ~30 respiratory conditions, expanding toward ~50. | Patient describes symptoms on a tablet; AI asks follow-ups, reads ECG/X-ray captured by an assistant, proposes a plan — **and a human doctor signs it.** Vendor claims <0.3% pre-trial error rate. Regulatory approval targeted ~18 months out. This is the ceiling of current autonomy, and it still has a human signature. | `vendor` |
| AQ for Doctor Ant Group | China. 300,000+ verified physicians on the platform as of Aug 2026. | An AI agent conducts pre-visit interviews, assembles histories, answers routine questions, and writes follow-up summaries into the patient record. Validates the async-intake pattern at national scale. | `vendor` |
| On-prem open models | DeepSeek variants reported running inside the intranets of 260+ Chinese hospitals across 93.5% of provinces. | Data never leaves the hospital firewall. Efficacy claims in the press (−15% diagnostic errors, −90% radiology turnaround) are *not* independently verified — but the **deployment topology** is the lesson, and it is the one Indonesian law forces on us anyway. | `trade` |
| Ambient scribes DAX vs Nabla vs control | Pragmatic 3-arm randomised trial, 238 outpatient physicians, 14 specialties, ~48,000 visits. *NEJM AI*. | Roughly **16 minutes saved per 8-hour shift** and ~7% improvement in burnout scores. Clinicians actually used the scribe in only 30–34% of eligible visits. Real, but far below vendor marketing. Budget accordingly. | `peer-reviewed` |
| HealthBench Professional | 525 physician-authored clinician-facing tasks, triple-reviewed, difficulty-enriched ~3.5×. | GPT-5.4 in ChatGPT for Clinicians scored 59.0; base GPT-5.4 48.1; **physicians themselves 43.7**. The gap is largest in writing and documentation (64.1 vs 32.1). Models now exceed physician baselines on clinician-facing text work. | `preprint` |
| MedGemma Google, open weights | `revised v2` Corrected against the model card: **MedGemma 1.5 ships only as a 4B multimodal instruct model** (`medgemma-1.5-4b-it`). The 27B variants — text and multimodal, the latter trained on FHIR-shaped EHR data — belong to *MedGemma 1*, the earlier release. | Strong MedQA performance for the size class, fully fine-tunable, self-hostable, PHI never leaves your infrastructure. But there is no MedGemma 1.5 27B to standardise on, and §3 shows model choice swings safety behaviour enormously. **We benchmark a shortlist; we do not pre-commit.** | `model card` |
| Market context | OpenEvidence: ~$12B valuation, daily use by 40%+ of US physicians, 20M+ consultations/month, embedded in Mount Sinai's Epic. Hippocratic AI: $3.5B, 50+ health systems in 6 countries, 250M+ patient interactions. AMA: 72% of US physicians now use AI clinically, up from 48%. | Clinician-facing AI has crossed from pilot to infrastructure in high-income markets. Nobody has built the equivalent for a Southeast Asian public-payer system. That is the opening. | `vendor` |

*Evidence grade: `peer-reviewed` published in a journal with review · `preprint` arXiv/medRxiv, not yet reviewed · `vendor` company-reported, unverified · `trade` secondary press reporting.*

### The pattern across every credible deployment

Strip away the branding and the winners all have the same shape. The AI runs *continuously and silently*, not on request. It interrupts only on material risk. It never takes the decision — it takes the *work around* the decision. And in every single case where an AI proposes a treatment, a licensed human signs it. Penda's traffic-light interface is the cleanest expression of this: green means say nothing, amber means the clinician may look, red means the clinician must look and acknowledge before proceeding.

The AMIE (Video) architecture makes the same point from the other direction: Google did not build one model that talks to the patient and reasons. They built a *talker*, a *planner*, and a *perceiver* running in parallel — the patient-facing surface is deliberately separated from the clinical reasoning. That is the same separation §3 forces on us for safety reasons, arrived at independently for capability reasons.

That design is not a compromise. It is the reason the Kenya result exists at all — and it is why the Kenya result is more relevant to us than anything from Google or OpenAI's US work. Same resource constraints, same clinician mix, same imperative that the system work on a cheap Android tablet with unreliable connectivity.

---

<a id="s3"></a>

**§3 — COUNTER-EVIDENCE**

## What breaks, and why it breaks worst in exactly our use case

If we only read §2 we would build the wrong thing. The failure literature from the last twelve months is unusually specific, and one finding should reshape the product.

### Medical sycophancy is a catastrophic, unsolved failure mode

MedPRESS (August 2026) ran 600 medically-grounded five-turn dialogues across 20 model configurations, applying escalating patient pressure: personal experience, then social proof, then "external evidence," then direct challenge. The aggregate results:

| Turn | Pressure applied | Unsafe agreement rate | Safe stance held |
|---|---|---|---|
| Turn 1 | Initial query | 5.9% | 84.3% |
| Turn 2 | "But it worked for me" | 58.5% | 19.9% |
| Turn 3 | Social proof | 39.0% | — (46.3% ambiguous) |
| Turn 4 | Cited "evidence" | 73.4% | — |
| Turn 5 | Direct challenge | 75.7% | — |

*Aggregate across the full conversation: 50.5% unsafe agreement, 29.2% safe-stance adherence, and an **86.8% conversation-level failure rate**. Source: MedPRESS, arXiv 2608.02520.*

Three details make this worse for us, not better:

- **Symptom triage was the most vulnerable category** (55.5% unsafe agreement, models flipping at a mean of turn 1.82) — and symptom triage is precisely the patient-facing surface we would build first.
- **Small open models were the worst.** Gemma-3-4B: 67.9%. Gemma-3-12B: 67.2%. DeepSeek-V4-Flash: 66.1%. The best was GPT-5.4-mini at 21.9%. Our on-prem, cost-driven instinct points directly at the most sycophantic tier of models.
- **Model choice moves this more than anything else we control.** The spread across the tested configurations ran from 21.9% unsafe agreement (GPT-5.4-mini) to 67.9% (Gemma-3-4B) — a 3× difference on the metric that matters most. Medical fine-tuning helps materially but does not solve it (MedGemma variants are reported in the mid-40s versus low-to-mid 60s for their base Gemma counterparts). This is the strongest argument for benchmarking a shortlist on our own Indonesian pressure suite rather than picking a model on MedQA scores.
- **Prompting barely helps.** An explicit anti-sycophancy instruction bought ~14 percentage points and delayed the flip from turn 1.63 to 2.41 — but conversation-level failure remained at 77.8–82.5%. This cannot be prompt-engineered away.

> **Design consequence**
>
> A free-form, multi-turn, patient-facing symptom chatbot is not a product we can safely ship in 2026, at any model tier. Patient-facing conversation must be **structurally constrained**: bounded history-taking with a fixed schema, no negotiation of clinical conclusions with the patient, and every clinical assertion routed through a deterministic gate before it reaches a human. The patient talks to an *interviewer*, not an *advisor*.

### Triage looks great in aggregate and hides the only error that kills people

A 2026 comparative study found an LLM triage architecture reaching F1 0.900 and 90.0% exact agreement with ground truth, versus 0.303 for nurse triage in the same dataset. Enormously impressive — except the highest-acuity class was 0.61% of the sample (4 of 657 cases), so undertriage risk was effectively unmeasured. Separate 2026 work found that methods which reduce overtriage do not reliably reduce undertriage, and audits have documented gender and proxy-variable bias in LLM triage. **Aggregate triage accuracy is a vanity metric. Red-flag recall on adjudicated high-acuity cases is the only number that gates deployment.**

### The known weak spots line up with our market

HealthBench's own analysis found that model performance is highest on emergency referrals and communication, and *lowest* on context-seeking, health-data tasks, and **global health**. AMIE, the strongest diagnostic system in the literature, lost to human PCPs specifically on management-plan practicality and cost-effectiveness — which under BPJS capitation and the Formularium Nasional is the constraint that matters most in Indonesia. And the ambient scribe RCT is a reminder that even the "easy," non-clinical wins deliver ~16 minutes a shift, not the hours vendors imply.

None of this says don't build. It says: the reasoning is good enough, the resilience under pressure is not, and the localisation gap is real and measurable. Our engineering budget should be weighted accordingly — heavier on guardrails, evaluation, and Indonesian grounding than on model work.

---

<a id="s4"></a>

**§4 — LOCAL CONSTRAINTS**

## Six Indonesian facts that determine the architecture

Most of the design is already decided by law and by the shape of the network. Better to discover that now than in month nine.

### 1. The shortage is real, and it is a specialist and distribution problem

Indonesia sits at roughly 0.45–0.5 doctors per 1,000 by Ministry of Health figures (the World Bank recorded 0.69 in 2022), against a WHO reference of 1.0. In June 2026 the Health Minister put the general-practitioner shortfall at **93,200 by 2032** — a projected need of 255,420 against a projected supply of 162,220 — in the ministry's first national workforce projection calculated down to district level. Specialists are worse: 47,454 as of December 2023, a ratio of 0.17 per 1,000 against Bappenas' target of 0.28 — a gap of roughly 29,000 specialists. And they are concentrated in Java and Bali. A 50-hospital network outside those islands is not short of *doctors* so much as short of *specialist judgment at the point of care*. That points the product at decision support and referral triage, not at replacing the generalist who is already there.

### 2. Your hospitals are small — and as of June 2026 the labels changed

`revised v2` Sources differ on the exact split and the year: a 2021 count of ~2,373 general hospitals gives 48.3% class C and 34.9% class D; a 2026 analysis of 3,216 hospitals gives 54.0% and 27.3%. Both land in the same place — **roughly four in five Indonesian general hospitals sit in the bottom two tiers** — so use the range, not a false-precision figure. Design for that reality: no on-site radiologist, thin IT staff, intermittent connectivity, cheap Android hardware, and staff whose digital readiness varies enormously between sites. Anything that assumes an Epic-grade EHR or a hospital data-science team will not deploy.

> **`revised v4` The classification regime: PP 28/2024 → Permenkes 11/2025 → Permenkes 6/2026**
>
> The shift away from bed-count classes began with **PP 28/2024**, the implementing regulation of the Health Law, and was carried into **Permenkes 11/2025** (enacted 3 October 2025) — an omnibus setting risk-based business-licensing and product/service standards across the health subsector, which revoked Permenkes 26/2018. **Permenkes No. 6/2026 on Hospitals** then consolidated the field: enacted 4 June 2026, promulgated 12 June 2026, revoking **21 prior regulations** including Permenkes 3/2020 on classification and licensing and Permenkes 40/2022 on technical requirements. Four provisions matter to us:
>
> - **Classification is capability-based and per service group.** Article 12 grades each service group as *dasar* (basic), *madya* (intermediate), *utama* (advanced) or *paripurna* (comprehensive), assessed on six axes: diagnoses, procedures, staff competency, facilities, infrastructure and equipment. A hospital can be *paripurna* in cardiology and *madya* in orthopaedics. There is no longer any such thing as "a class C hospital." Minimum thresholds are set by ownership: domestic-investment hospitals need at least 50 beds and two *dasar*-classified services (Art. 10(1)); foreign-investment hospitals need 50 beds with one top-tier service, or 200 beds with two (Art. 10(2)).
> - **Article 74 requires digital reporting of all hospital operations** into the national health information system — clinical, quality, workforce, financial and educational. Audited annual financial statements become mandatory.
> - **Tariffs are capped.** A national tariff framework set by the Minister, with maximum ceilings set by provincial governors, reviewed every five years.
> - **Accreditation becomes a sanction.** Article 80's escalation runs warning → written warning → fine → accreditation adjustment or revocation → licence revocation, with authority to skip steps in severe cases.
>
> Transition is **two years from 12 June 2026** for operating hospitals, four for former class-D *pratama* permit holders. Implementing technical regulations defining each tier are still pending.

**Read this as three things at once.** As a correction: every "class C/D" in this memo now describes capability, not a legal category. As a validation: the regulator has independently converged on the same object we designed in §6 — a per-site, per-service capability record covering diagnoses, procedures, competencies and equipment. And as a commercial opening: the hospital association's own reading is that naming a service is no longer sufficient, hospitals must evidence that it happens, which is precisely what coded encounter data proves. Every hospital in Indonesia needs a structured capability record with evidence behind it by mid-2028, and nobody is selling one.

The tariff ceiling deserves its own sentence, because it decides the business case. **If a hospital cannot raise prices, revenue growth must come from coding what it actually did and seeing more patients with the doctors it has.** That is not our pitch being convenient — it is the only remaining lever the law leaves open.

### 3. Health data must stay in Indonesia — this is not negotiable

> **GR 28/2024**, implementing the Health Law (UU 17/2023), requires health data and health information systems to be stored and processed in data centres located within Indonesian jurisdiction — hospitals, clinics, and digital health platforms alike. **UU PDP 27/2022** has been fully in force since 17 October 2024, with enforcement currently under Komdigi's Directorate General of Digital Space Supervision and a dedicated authority planned.

`revised v2` The precise requirement is **no uncontrolled cross-border processing of identifiable clinical data** — not "frontier models are impossible." Three routes satisfy it: open-weight models on Indonesian infrastructure; a sovereign in-country deployment from a frontier vendor; or de-identification to a standard we can defend to a regulator. Chambers' 2026 Indonesia guidance reads GR 28/2024 as requiring health-data databases to be hosted in-territory while permitting third-party storage subject to conditions, which leaves the sovereign-deployment route open.

For the MVP the practical answer is still the conservative one: **in-country open weights for anything touching PHI**, frontier models confined to de-identified evaluation, distillation, and offline work. But we should keep a sovereign frontier deployment live as a commercial conversation, because §3 shows the frontier tier is meaningfully safer under adversarial pressure. Fortunately §10 shows the economics agree with the law either way.

### 4. SATUSEHAT is both the obligation and the wedge

SATUSEHAT is the national FHIR R4 platform; hospitals push encounter data to it over REST. Over 1,200 hospitals were flagged non-compliant against a June 2026 deadline, with sanctions from the Directorate General of Health Services. Nominally 96% of 3,239 hospitals have an EMR (Oct 2025), but close to 500 aren't using it across the six core services. Meanwhile a Black Book market survey published 4 February 2026 reports that 80% of Indonesian hospitals are active in at least one EHR initiative, **43% intend to replace or materially re-platform their core SIMRS/EHR within 24 months**, **61% prioritise "coding and BPJS/INA-CBG claims workflow automation as the fastest near-term ROI lever,"** and **58% have no dedicated interoperability operations function**. `trade` It is a vendor press release with no disclosed sample size or methodology — directional, not a measurement — but the 61% figure names our phase 1 as the market's own stated top priority, and the 58% explains why they cannot build the FHIR layer themselves.

Read that as a commercial map. The compliance pain is acute, the budget is unlocked, and the buying criterion is already "does it emit valid FHIR and clean claims." **If our clinical agent also happens to be the thing that makes a class-D hospital SATUSEHAT-compliant and its INA-CBG claims clean, it sells itself and pays for the clinical pilot regardless of clinical outcome.** Note also the documented integration pain — the JMIR analysis of the developer hub found server issues (61 mentions) and data-mapping issues (37) dominating. Budget real engineering for the FHIR profile mapping; it is not a weekend.

### 5. Clinical content and payment rules are national, published, and bindable

Kemenkes publishes PNPK (national clinical service guidelines, with a 2026 collection), IDI publishes PPK for primary care, and the **Formularium Nasional** is binding for JKN patients. That is a huge advantage over building in a market with fragmented guidelines: we have an authoritative, citable, machine-ingestible corpus. AMIE's Nature result is essentially "long-context grounding in official guidelines plus a formulary beats ungrounded reasoning" — the Indonesian equivalents exist and are free.

### 6. The epidemiology tells us which three pathways to build

Acute upper respiratory infection (J06.9) alone is ~6% of BPJS capitation visits — around 650,000 encounters. About 30% of capitation visits are promotive/preventive, 78% of those delivered by Puskesmas. And Indonesia carries the world's second-largest TB burden: roughly 842,000–1,000,000+ cases a year, ~10% of the global total, with about 32% undetected or unreported. WHO has recommended computer-aided detection on chest X-ray for screening in people aged 15+ since 2021 and **approved six CAD products for that use in June 2025** — those are procurable today.

`revised v2` An earlier draft treated TBScreen.AI, the UGM-led Indonesian CAD effort, as a finished product. It is not: the public record describes a development programme with a 2026 prospective validation protocol against radiologists and final patient diagnoses, positioned as a screening aid. It is a valuable local research partner and the right benchmark to measure ourselves against — it is not a shipping radiologist replacement, and we should not plan around it as one.

> **TB screening is the one place where AI genuinely outperforms the human alternative available in a class-D hospital — because the alternative is no radiologist at all.** It is also the highest-visibility national priority. It should be in the MVP for that reason alone.

**Also on the record**

- **Telemedicine:** Permenkes 20/2019 defines the service categories; UU 17/2023 Art. 172 covers facility-to-facility and facility-to-community delivery. Providers' medical staff must hold STR and SIP.
- **Medical device software:** `corrected v4` An earlier draft called Permenkes 11/2025 "the SaMD framework," which is loose. Its actual title is *Standar Kegiatan Usaha dan Standar Produk/Jasa pada Penyelenggaraan Perizinan Berusaha Berbasis Risiko Subsektor Kesehatan* (3 October 2025) — an omnibus of risk-based licensing standards covering the health subsector, which is why the same instrument governs both hospital service standards and medical device product standards. The underlying device classification (Class A–D by risk, standalone software included) traces to **Permenkes 62/2017**. In practice: SaMD registers through REGALKES on the ASEAN CSDT template, requires IEC 62304 compliance, software architecture and cybersecurity documentation, clinical evaluation evidence, and an Indonesian-language IFU; the NIE is valid five years. Note the operational risk — Kemenkes suspended REGALKES from 15 December 2025 to 9 January 2026 to align the platform with Permenkes 11/2025, and NIEs that expired inside that window lapsed on 1 January 2026. *Assume we need a registration; start the file in month one, not month twelve.*
- **AI-specific rules:** GR 28/2024 names AI as part of the national health information system but sets no permitted-use rules. A Presidential Regulation on AI ethics and safety is expected to convert voluntary guidance into a mandatory high-risk framework. We should build to the strictest plausible reading now — glass-box logic, full audit trail, named accountable clinician — rather than retrofit.
- **Language:** Bahasa Indonesia plus Javanese and Sundanese in the regions. Zero-shot Whisper large-v2 on Javanese scores 89.4% WER — unusable. Fine-tuned, it reaches 13.77%. ASR fine-tuning on our own recorded consultations is a required workstream, not an optimisation. There is already a published proof-of-concept for LLM transcription and summarisation into ePuskesmas.

---

<a id="s4a"></a>

**§4a — THE JAPAN PRECEDENT**

## What crosses the water, and what drowns

The same system is being built for a client in Japan. That changes the useful question. It is no longer "can this be done" — Japan answers that. It is "which parts are portable, which are configuration, and which have to be thrown away." This section answers that component by component, and is blunt about the four things that do not transfer.

### 1. Japan validated the reframe by legislation

Japan does not have a doctor shortage. It has a doctor-*hours* shortage, and the government created it deliberately. In April 2024 the physician work-style reform capped overtime at **960 hours a year** for most doctors (Level A), with higher ceilings for designated emergency, community-care and training roles. `partial` Sources disagree on those higher figures — 1,440, 1,860 and 1,920 hours all appear — so quote the 960 and describe the rest qualitatively. A Ministry of Health survey in December 2024 found **5.3% of hospitals, around 300 facilities, already reporting fewer physicians dispatched to rural areas**; a further ministry survey reported in July 2026 found roughly **15% of hospital doctors still exceeding the cap**.

What followed matters more than the cap. The Ministry published an official **task shift / task share list**: preliminary questioning at first consultation, explaining procedures and admission, medication guidance, proxy entry into medical documents, plus procedures moved to nurses and technologists. Set that beside §5's decomposition and it is the same list. We derived it from what a model can safely draft; Japan derived it from what a non-physician may legally do.

> **The 60–70% target is not a bet.** It is the published policy of a G7 health ministry, minus the AI. That is a stronger citation than anything in §2.

### 2. Everyone who entered that market entered through the same door

| Player | What actually shipped | The lesson |
|---|---|---|
| Ubie | AI pre-consultation questionnaire, then generative document drafting. Per its 5 Feb 2026 release: **100 hospitals including 10+ university hospitals** as of January 2026; the wider series is in 1,800+ institutions across all 47 prefectures. Named results: Keiju General **−42.5%** on discharge nursing summary time and −27.2% on reported psychological burden; Nanbu Tokushukai ~200 staff-hours freed monthly; Kameda General ~30% off cancer-registry data gathering; **Kyushu University Hospital expects >¥65M/year of revenue improvement**. `vendor` | Pre-visit intake plus documentation is a real business at national scale — exactly our phase 1. The Kyushu figure is the one to notice: a Japanese hospital booking our coding-capture thesis as revenue, not as time saved. |
| Fujitsu Japan × JCHO Osaka Hospital<br>(with Fortience, Microsoft Japan) | Agreement signed 13 Feb 2026. Generative AI for discharge summaries and nursing handovers, operational June 2026. Scope explicitly includes internal AI guidelines, information infrastructure and operational governance. `trade` | The incumbent EMR vendor entered at documentation, not diagnosis — and roughly a third of the project is governance rather than software. |
| Hippocratic AI × EUCALIA | Japanese-language patient-facing agent from May 2025, described in its own headline as **non-diagnostic**: scheduling, follow-up outreach, chronic-care check-ins, medication adherence. `trade` | The best-funded patient-facing clinical AI company in the world drew the same line we drew in §1, and put it in the press release. |

Three independent, well-capitalised teams. None sold a diagnosing doctor.

### 3. Four things do not transfer

|  | Japan | Indonesia | Consequence |
|---|---|---|---|
| **The sale** | Cost-out, and it is survival. ~60% of 1,800 surveyed hospitals posted an ordinary loss in H2 2024; 68% of private hospitals were loss-making in 2024; 86% of city-hospital association members were in ordinary deficit by Aug 2025; ~70% of national university hospitals ran deficits in FY2024, ¥28.5bn combined. | Revenue capture and throughput. Private groups are profitable — Siloam reports a 24% EBITDA margin. | Same software, opposite conversation. Rebuild the ROI model from scratch. |
| **Adoption pull** | The fee schedule *pays* for it. The FY2026 revision abolished the older digital-DX and information-acquisition additions and created the Electronic Clinical Information Sharing System Setup Addition — up to 15 points at first visit, 2 at follow-up, up to 160 on the first inpatient day. | **Nothing.** No INA-CBG line item rewards digital maturity. Adoption rests entirely on an internal mandate. | The single largest reason to expect Indonesian adoption to lag the Japanese curve. Change management is a budget line, not an afterthought. |
| **Regulation** | PMD Act; software for diagnosis, treatment or prevention is a device at Class II+. PMDA updated its core SaMD guidance on **5 June 2026** covering AI/ML validation, cybersecurity and revalidation on retraining. ~40 AI-enabled products among 151 SaMD approvals. Two-stage adaptive approval with real-world evidence; rolling priority-review designation from FY2026. | Permenkes 11/2025 and REGALKES, but **no AI-specific pathway at all**. Kemenkes was still running a national conference on health-AI governance on 8–9 June 2026, with informed-consent standards and ethics-committee capacity on the agenda. | Backwards from the intuition: Japan's mature pathway means a Japanese product *can* aim at a regulated diagnostic claim, because there is a door. With no door and no precedent, the Indonesian product must sit deliberately **below the device threshold** — a drafting tool with no clinical effect until a licensed doctor signs. Which is the architecture in §6 already. |
| **Evaluation and language** | `corrected v4` Japanese researchers ran HealthBench's 5,000 scenarios through machine translation and used an LLM-as-judge to find where the rubrics misalign with Japanese guidelines, health-system structure and cultural norms. GPT-4.1 dropped modestly on rubric mismatch; a Japanese-native open model (LLM-jp-3.1) **failed badly on clinical completeness**. An earlier draft of this memo described that paper as "HealthBench-JP, 50 Japan-specific scenarios" — it is a gap analysis, not a new 50-case benchmark, and the correction matters because the real finding is stronger: translation alone is demonstrably not enough. Japan also has JMedBench and JMed48k, and a domestic sovereign model in NTT's tsuzumi 2 (20 Oct 2025), already deployed in the medical sector. | **None of it exists in Bahasa Indonesia.** No adapted clinical benchmark, no medical leaderboard, no domestic clinical model. And consultations are frequently not in Bahasa at all — zero-shot Javanese ASR sits at 89.4% WER against 13.77% fine-tuned (§4). | The evaluation harness's *shape* ports; every case, rubric and gold answer must be rebuilt. See the box below — this is the most under-rated asset in the whole plan. |

*Reusing the Japanese business case in an Indonesian deck would be the clearest possible signal that nobody re-underwrote it.*

> **The benchmark that doesn't exist is the moat**
>
> Japanese researchers demonstrated, with numbers, that a machine-translated American benchmark misaligns with local guidelines and health-system structure. Indonesia has no equivalent study and no adapted benchmark, which means nobody — not us, not a competitor, not Kemenkes — can currently answer "is this medical AI safe for Indonesian practice" with evidence. If we build a few hundred adjudicated Indonesian cases with rubrics against PNPK, PPK and Fornas, we own the only instrument in the country that can answer it. That is a regulatory conversation-opener, a competitive barrier, and something publishable. Budget clinical reviewer hours for it explicitly: it is the one part of the eval harness that cannot be generated.

### 4. One thing runs the other way, and nobody expects it

On integration, **Indonesia is ahead of Japan.** Japan's national exchange — the Electronic Medical Record Information Sharing Service — runs on HL7 FHIR, carries "three documents and six information sets," entered model operation in 2025 and reaches full operation around winter 2026. Electronic record adoption in Japanese general hospitals only recently passed 50%, and clinical notes remain unstructured free text.

SATUSEHAT is FHIR R4, has a public developer portal with OAuth 2.0, and is *already mandatory* with sanctions live and 1,200+ hospitals flagged (§4). Compulsory beats incentivised. And the EMR layer inverts the same way: Japan's hospital systems are entrenched proprietary estates where every integration is a vendor negotiation, while Indonesia's dominant small-hospital system is open source with an existing bridging package (§0). **Japan had to ask permission. We have the source code.** That is a real reason the Indonesian build can reach further into the consultation form than the Japanese one can.

### 5. The failure mode is different, and the safety bar goes up

`corrected v5` An earlier draft argued that in Indonesia the AI "substitutes for a doctor who is not there." That contradicts our own thesis and should not be used. **In both countries the AI takes work off a doctor who is present and signing.** The system never covers for an absent clinician; that is the substitution model §1 rejects.

What actually differs is **supervisory depth** — how much clinical backup stands behind the doctor who signs. In a Japanese hospital, a physician reviewing an AI draft sits inside a dense support structure: colleagues to consult, a radiologist on site, specialists down the corridor, and a workforce abundant enough that a bad output has several chances to be caught. In a smaller Indonesian hospital the same draft is reviewed by a general practitioner who may have no radiologist, no on-site specialist, and nobody to check with before the patient leaves.

The instinct is that a thinner system licenses a lower bar, because the alternative is worse anyway. **The opposite holds.** Fewer people downstream can catch the machine's error, so more of the checking has to happen inside the machine. The deterministic gate, the abstention floor, the site-capability check and the sycophancy suite are not Indonesian refinements — they are the compensating controls for thinner review capacity, and they are why §9's gates are set where they are.

### 6. The reuse ledger

What a second deployment actually costs, component by component, is set out in **BUILD** §2b. The headline: roughly **40% carry-over by engineering effort** — the graph, checkpointing, audit trail, FHIR client and eval scaffolding — and it is the slowest, most expensive 40% to build from scratch. The 60% rebuilt is mostly content and rules: corpus, coding, evaluation cases, language, drug tables and offline behaviour.

The strategic consequence: build this as the **second instance of a platform**, not a bespoke Indonesian project, with everything national isolated into swappable packs. One rule enforces it and is free to adopt today: *nothing in the clinical core may name a country, a payer, a drug or a guideline.* That is a grep in CI, and it is the difference between an AI project and an AI-levered platform.

### 7. What Japan cannot tell us

- **Adoption.** Japan has reimbursement pull, high digital literacy, and doctors under a legal hours cap who are personally motivated to offload work. Indonesia has none of the three. Japan's adoption curve is an upper bound, not a forecast.
- **Infrastructure.** No part of the Japanese build had to survive a power cut or a dropped connection mid-consultation. That entire engineering workstream is unvalidated by this precedent.
- **Clinical mix.** Japan is an ageing, chronic-disease, high-imaging system. Indonesia is dual-burden — TB, dengue and maternal care alongside a fast-rising diabetes and hypertension load. The high-value pathways differ, so §7's pathway selection cannot be inherited.
- **Outcomes.** Neither market has produced a randomised trial. Japan's deployments report document-time savings — real, measurable, and about workload rather than clinical outcome. That is the honest ceiling of what either country's evidence currently supports.

> **The line to say in the room:** Japan proves the machine works and the market is real. It does not prove it works here — different money, different failure mode, no benchmark, no drug database, no power. Reuse the plumbing, rebuild the country, and build the Indonesian evaluation set nobody else has, because that is the part that turns a second deployment into a franchise.

---

<a id="s5"></a>

**§5 — THE DECOMPOSITION**

## Where the 60–70% actually comes from

This is the answer to the mandate. A consultation breaks into eleven tasks. Automate the eight with evidence behind them and you get the number — without ever touching the signature.

| Task | Share of minutes | Automatable now | Evidence base | Regulatory exposure |
|---|---|---|---|---|
| Registration, identity, BPJS eligibility | 8% | 100% | Commodity | `none` |
| History taking — HPI, ROS, meds, allergies | 22% | 85% | AMIE at BIDMC; Ant AQ at 300k physicians | `low` |
| Vitals & basic examination capture | 10% | 40% | Needs a human or device; AI guides acquisition (POCUS AI guidance now FDA-cleared for novice users) | `low` |
| Differential generation | 8% | 70% | AMIE: 90% containment, 75% top-3 — as a *suggestion* | `medium` |
| Red-flag detection & investigation ordering | 7% | 60% | Penda: −16% diagnostic error as a safety net | `medium` |
| **Committing to a diagnosis** | 4% | 0% | Not delegable. This is the licensed act. | `prohibited` |
| Prescribing within Formularium Nasional | 9% | 70% | AMIE disease-management + RxQA; must be deterministically constrained, never LLM-judged | `high` |
| Explaining the plan to the patient, in their language | 11% | 80% | HealthBench: communication is models' *strongest* theme; they beat physicians on tailored explanation | `low` |
| Documentation → SOAP → ICD-10 → FHIR → SATUSEHAT → INA-CBG | 14% | 90% | HealthBench Professional: 64.1 vs physicians' 32.1 on writing/documentation. Highest ROI, zero clinical risk. | `none` |
| Follow-up, adherence, chronic titration | 5% | 70% | AMIE longitudinal (Nature); Hippocratic voice agents at scale | `medium` |
| Referral packaging to a specialist | 2% | 80% | Structured summarisation; directly addresses the specialist-distribution gap | `low` |

*`revised v2 — arithmetic corrected` Share of minutes is a working estimate for a ~10-minute class C/D outpatient consultation, to be replaced with time-and-motion data from our own sites in week 1 of the pilot. Weighted automatable share on these estimates: **73.3% of task-minutes** (an earlier draft said 64%, which did not follow from this table). Weighted share of *accountability* transferred: **0%**.*

Two honest caveats before anyone quotes this. First, the corrected weighted figure is **73.3%**, not the ~64% an earlier draft claimed — the brief's 60–70% target looks achievable with headroom, which is a better answer than the one I first gave. Second, and more importantly: *every number in the first two columns is my estimate, not a measurement.* They are informed by the literature and by what these tasks look like, but no one has timed a class C/D Indonesian consultation for this purpose. The defensible statement today is "a large majority of consultation work appears addressable"; the precise figure is what weeks 1–2 of the pilot exist to establish.

What does not move is the 4% we deliberately do not touch — the act of committing to a diagnosis and owning it. That is the entire legal and ethical substance of being a doctor, and it is also, conveniently, the cheapest 4% to leave alone.

Sold to the board, the pitch is not "we replace two-thirds of a doctor." It is: **each doctor in the network sees roughly 2.5× the patients at a lower error rate.** Same throughput. No regulatory cliff.

---

<a id="s6"></a>

**§6 — ARCHITECTURE**

## Reference architecture

Six layers. The two that matter most are the deterministic gate — which is deliberately not an LLM — and the residency boundary, which is drawn by GR 28/2024 rather than by us. This section describes the target; [§6a](#s6a) lists every assumption it stands on and which of them are still unverified.

```
┌── INDONESIAN DATA-RESIDENCY BOUNDARY — GR 28/2024 ─────────────────────┐
│                                                                        │
│      Patient intake — kiosk, phone, nurse station                      │
│      Bahasa · Jawa · Sunda   ·   voice + structured touch              │
│                        │ symptoms, meds, allergies                     │
│   ┌──────────────┐     ▼                                               │
│   │ LONGITUDINAL │  History agent — async, before the doctor           │
│   │   PATIENT    │──▶ fixed schema · no clinical advice to the patient │
│   │    STATE     │     │ structured history + device data              │
│   │              │     ▼                                               │
│   │ history·meds │  Reasoning core             ◀── Grounding corpus    │
│   │ labs·imaging │  model router · in-country      PNPK · PPK · Fornas │
│   │ prior visits │  GPU · shortlist benchmarked    BPJS rules          │
│   │              │  never pre-committed            versioned           │
│   │              │     │                                               │
│   │              │     │ every            ◀── Hospital capability      │
│   │              │     │ candidate            stocked drugs · tests    │
│   │              │     │ output               specialists · referral   │
│   │              │     ▼                      BPJS coverage rules      │
│   │              │ ╔═══════════════════════════════╗                   │
│   │              │ ║  DETERMINISTIC GATE           ║                   │
│   │              │ ║  — deliberately not a model — ║                   │
│   │              │ ║  9 checks · plain code · diffable in git          │
│   │              │ ╚═══════════════════════════════╝                   │
│   │              │     │ only what passes — failures never render      │
│   │              │     ▼                                               │
│   │              │  Traffic light, inside the existing EMR             │
│   │              │  ● silent    ● optional    ● must acknowledge       │
│   │              │     │ fires at defined EMR events                   │
│   │              │     ▼                                               │
│   │              │ ╔═══════════════════════════════╗   Eval &          │
│   └──────────────┘ ║  CLINICIAN — STR + SIP        ║──▶ telemetry      │
│           ▲        ║  the only signer              ║   override rates  │
│           │        ╚═══════════════════════════════╝   red-flag recall │
│      writes back        │ signed encounter                             │
│                         ▼                                              │
│      FHIR R4 bundle → SATUSEHAT · ICD-10 · INA-CBG claim draft         │
│                                                                        │
└────────────────────────────────────┬───────────────────────────────────┘
                                     ╎  NO PHI CROSSES THIS LINE
                        ┌ ─ ─ ─ ─ ─ ─┴─ ─ ─ ─ ─ ─ ┐
                          Frontier API — OFFLINE
                        │ eval grading · distillation│
                          synthetic case generation
                        └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

***The gate is what makes the rest deployable.** The product is the clinical state, the workflow and the reasoning; the gate is the thing that lets any of it near a patient. Everything above it is probabilistic and replaceable — models will get better and we will swap them. Everything at the gate is deterministic, auditable, and version-controlled: a red-flag rule engine, a drug-safety checker, and a hard membership test against the Formularium Nasional. An LLM claim that cannot be resolved to a citation in the grounding corpus is dropped before a human ever sees it. This is what makes the system explainable to Kemenkes, insurable, and resistant to the sycophancy failure in §3 — because the model is never the last word.*

### `revised v2` The gate, specified

An earlier draft described the gate as three checks. It needs nine, and checks 7 and 8 are the ones most often omitted — a system that cannot decline to answer will confabulate under exactly the conditions where confabulation is most dangerous.

1. **Red-flag rules** — deterministic, protocol-derived, evaluated on the structured state, never on model output.
2. **Guideline conformance** — does the proposed plan match PNPK/PPK for this presentation?
3. **Drug safety** — dose, interaction, allergy, renal and hepatic adjustment, pregnancy category.
4. **Contraindication check** — against the patient's own recorded conditions, not a generic profile.
5. **Formularium Nasional membership** — hard set test; a non-Fornas drug for a JKN patient never renders.
6. **Citation resolution** — every clinical assertion must resolve to a versioned document in the grounding corpus.
7. **Missing-data check** — is there enough information to support this conclusion at all? If not, the output is a request for information, not a recommendation.
8. **Uncertainty floor** — below a calibrated confidence threshold the system abstains and escalates rather than producing a low-confidence plan.
9. `v3` **Executable here** — is the proposed plan actually deliverable *at this hospital, today*? Is the drug stocked, is the test on site, does the specialist exist, does BPJS cover it? A plan that fails this check is not a recommendation, it is a referral.

That last check deserves more attention than it usually gets. The one axis on which AMIE lost to human PCPs was the **practicality and cost-effectiveness of management plans** — and the reason is structural, not a model weakness. Human doctors know what their hospital can actually do. A recommendation to order a test a class-D hospital does not have is worse than useless: it burns clinician trust and it is exactly the failure that makes staff stop opening the tool. The hospital capability registry is cheap to build — it is a maintained configuration file, not a model — and it is what converts a correct plan into an executable one. It belongs in v1, not on the roadmap.

### Notes on each layer

- `revised v2` **Longitudinal patient state.** The durable asset is not the agent graph — it is the structured, versioned representation of a patient evolving over time. A doctor does not encounter "a diagnosis task"; they encounter a person with a history. This matters most for the chronic pathway, and it is what the AMIE disease-management result actually depends on. Everything else in this diagram is replaceable; this is the thing that compounds and the thing a competitor cannot copy.
- **Edge.** Offline-capable PWA on cheap Android tablets. Store-and-forward when connectivity drops — this is a class-D hospital, not a Jakarta private group. Peripherals in scope: digital X-ray with on-device CAD for TB, handheld ultrasound with AI acquisition guidance (now FDA-cleared for novice users, including a blind-sweep gestational-age tool), ECG, BP, SpO₂, glucometer.
- **History agent.** Async, before the doctor is in the room — this is the AMIE and Ant AQ pattern, and it is where the largest single block of minutes lives (22%). Critically: a bounded interviewer working to a fixed schema. It does not answer clinical questions, does not negotiate, does not advise. §3 forbids it.
- `revised v3 — was inconsistent with §2` **Reasoning core.** An earlier draft named "MedGemma-class 27B open weights" here, which contradicts the §2 correction: MedGemma 1.5 ships only at 4B. The layer is a **model router over a benchmarked shortlist** — medical-tuned and general open weights in the 4–30B range, fine-tuned on our own de-identified corpus and on Indonesian clinical language, sized for in-country GPU. No model name is hard-coded anywhere except the router config, because §3 shows model choice swings unsafe-agreement rates threefold. Frontier models are used *offline* to generate training data, grade evals, and distil — never in the live PHI path.
- **Grounding corpus.** PNPK, PPK primer, Formularium Nasional, BPJS/INA-CBG rules — versioned, with every clinical assertion citation-bound. AMIE's Nature result says this is where the management-quality gains come from.
- **Presentation.** Inside the EMR the clinician already uses, triggered on defined events (field blur, order entry, plan commit) — Penda's exact pattern. Green is silent. That silence is what keeps the amber and red signals credible.
- **Emission.** The FHIR/SATUSEHAT/INA-CBG path is a separate, boring, high-value pipeline. It is the commercial wedge from §4 and it must work even when the clinical layer is switched off.

---

<a id="s6a"></a>

**§6a — ASSUMPTIONS**

## Everything §6 is standing on

§6 was written as a target architecture. For a prototype that is the wrong register — a diagram is only as good as the assumptions holding it up, and mine were implicit. Here is every load-bearing one, what I could actually verify, and the cheap test that settles it in weeks 1–2.

| # | Assumption | What I found | Conf. | If wrong | Week 1–2 test |
|---|---|---|---|---|---|
| A1 | We can inject a traffic light *inside* the existing SIMRS, firing on field blur and order entry. | `RESOLVED — see §0` Commercial vendors (DHealth, Valtera, SistemKesehatan.id, Kardia) advertise Open APIs, but a data API is not a UI extension point. The answer came from elsewhere: **SIMRS Khanza, the dominant system in the class C/D segment, is open source**, on GitHub, with an existing `src/bridging/` package integrating BPJS PCare, Siranap and Dukcapil. We have the source. | `verified` | Was the design-killer. Now bounded: the risk is fork maintenance across a heterogeneous estate, not feasibility. | Stand up Khanza locally, add a no-op panel to the outpatient consultation form, and time the round trip. One engineer, two days. |
| A2 | Patients will complete an async pre-visit interview themselves. | ~40% of Indonesians have limited digital literacy. Rural reliable connectivity is ~25% against ~75% urban; Jakarta internet access ~85% versus ~26% in Papua. AMIE's cohort skewed younger and sat in a US academic centre. The literature's recommendation for this population is explicitly *assisted* digital models. | `unverified` | Threatens the single largest block of task-minutes (22%). Not fatal — it changes *where* the interview happens. | Run the interview 30 times on paper with a nurse before writing any code. Measure completion, time, and how often the nurse has to intervene. |
| A3 | A drug interaction, dosing and contraindication knowledge base for Indonesian products exists to power gate check 3. | **It does not.** BPOM publishes a product *registration* database (badanpom.id, third-party API at apiindonesia.id) — that is marketing authorisation data, not clinical pharmacology. There is no Indonesian RxNorm or First Databank equivalent. | `verified — gap is real` | Gate check 3 has nothing to run on. This was the biggest hole in §6. | Count the distinct molecules across the three MVP pathways. If it is under ~100, curate manually against Fornas and an international reference; only license a commercial database if it is larger. |
| A4 | The Formularium Nasional is machine-ingestible. | Fornas is issued as a ministerial decree — the current one is Kepmenkes HK.01.07/MENKES/1199/2025, published January 2026 — with a portal at e-fornas.kemkes.go.id. Authoritative and public, but distributed as decree documents rather than a structured feed. | `partial` | Gate check 5 is a hard set-membership test and must be exact. A parsing error becomes a silent formulary violation. | Parse the decree to a structured table, then have a hospital pharmacist verify a 200-row sample. Track the update cadence — this file changes. |
| A5 | We can obtain SATUSEHAT write access. | Documented and tractable: OAuth 2.0 client-credentials, register the app in the developer portal for a client_id and secret, then four steps before submitting data — authenticate, register organisation structure, register location structure, store practitioner IDs. Verified facilities can delegate API access to verified EHR partners. | `verified` | Low. The path is published. | Get one site's Organization ID and push a single test Encounter to the sandbox. |
| A6 | We generate the INA-CBG claim. | Corrects a v1 overreach. INA-CBG has 1,075 case groups (786 inpatient, 289 outpatient), three severity levels and five regional tariff classes, and severity is assigned by the *official government grouper* from primary diagnosis, secondary diagnoses and procedures, through the E-Klaim application. | `verified — scope corrected` | None, once corrected. **We produce accurate ICD-10 and ICD-9-CM codes and feed the official grouper. We do not build a grouper.** | Take 50 historical encounters, code them with the model, run them through E-Klaim, and compare the resulting CBG against what was actually claimed. |
| A7 | In-country GPU is available at workable cost and latency. | Yes, and better than expected. Lintasarta (Indosat) runs GPU Merdeka, a sovereign AI cloud on 8× H100 SXM nodes; BDx opened Indonesia's first sovereign AI data centre in December 2024; Zankore — Indosat, Ooredoo, Nokia and NVIDIA — is targeting ~200 MW of GB300 capacity in H1 2027. | `verified` | Low. The §4 residency constraint and the §10 economics are both satisfiable today. | Benchmark the shortlist on GPU Merdeka. Measure end-to-end latency from a pilot site, not from Jakarta. |
| A8 | Connectivity and power are reliable enough for a live service. | Measured, at puskesmas level: 7.18% have no internet, 14.33% limited, 53.64% sufficient, 24.85% sufficient and fast — and **8.02% lack 24-hour electricity**. SATRIA-1 satellite capacity is being extended to 3T-region facilities. Hospitals will be better than puskesmas, but the class D tail overlaps. | `verified` | Confirms offline-first is mandatory, not defensive. A cloud-round-trip design fails at roughly one site in five. | Log connectivity and power at all three candidate sites for two weeks before committing to a site list. |
| A9 | We may train on our own patient data. | PDP Law 27/2022 treats health data as sensitive, requiring an explicit lawful basis; DPIAs are required for high-risk processing; processing anonymised data for research is not prohibited where compliant. Note that GR 28/2024 (health) and the PDP implementing regulation are different instruments and reporting on them is frequently conflated — including in some of the sources I read. | `partial` | Blocks fine-tuning and possibly the retrospective adjudication set — i.e. the evidence strategy. | Counsel question, week 1. Draft the DPIA and the consent language in parallel with the data pull, not after it. |
| A10 | ASR works on real clinic audio. | The Javanese figure I cited — 13.77% WER fine-tuned, against 89.40% zero-shot — comes from read speech, not noisy conversational medical dialogue with code-switching. No published benchmark for conversational Indonesian medical ASR was found; the ePuskesmas proof-of-concept exists but did not systematically evaluate medical terminology. | `partial` | Degrades documentation, the highest-ROI layer. Fallback is typed structured entry, which costs most of the time saving. | Record 50 real consultations at each site. Compute WER against human transcripts, separately for medical terms and for the rest. |
| A11 | PNPK and PPK cover our three pathways at usable specificity. | Kemenkes maintains a PNPK collection including a 2026 edition; IDI publishes PPK for primary care. Coverage of the specific pathways was not verified document-by-document. | `partial` | Gate checks 2 and 6 lose their referent; citations stop resolving. | Pull the actual documents for ARI, hypertension, T2DM and TB. Check they contain thresholds specific enough to encode as rules. |
| A12 | Portable X-ray with CAD is deployable at a class D site. | Heavier than v1 implied. An imported device needs an AKL izin edar (five-year validity) via REGALKES; X-ray additionally requires BAPETEN radiation compliance, an IDAK distribution licence with Electromedical Radiation scope, and a CDAKB certificate. Six CAD products carry WHO approval. | `partial` | Delays the TB pathway on regulatory and logistics grounds, not technical ones. | Check what X-ray hardware the three sites already have. Prefer CAD that runs on an existing machine over new hardware. |
| A13 | The hospital capability registry can be kept current per site. | No evidence either way — this is a new v3 component. Stock-outs are common in the Indonesian supply chain, so a stale registry is not a hypothetical. | `unverified` | Gate check 9 starts producing confidently wrong "executable" verdicts, which is worse than having no check. | Ask each site's pharmacy how often stock lists change and whether they can be read from the SIMRS. If not automatable, cap the registry at slow-moving facts. |
| A14 | Clinicians will act on amber and red alerts. | The evidence is mixed and mostly cautionary: in the ambient-scribe RCT, clinicians used the tool in only 30–34% of eligible visits. Penda got engagement, but they employed their clinicians and could mandate the workflow. | `partial` | The safety net exists and nobody looks at it. This is the most likely way the pilot fails quietly. | Instrument acknowledgement and override from day one of shadow mode. Treat engagement as a primary endpoint, not telemetry. |
| A15 | Indonesian physicians are available to adjudicate 1,500 encounters. | Not verified. §4 establishes that physician time is the scarcest resource in the system — which is precisely what the adjudication set consumes. | `unverified` | No gold set means no gates, no evidence, no NIE file, no publishable result. | Price it. Two physicians × 1,500 encounters at ~6 minutes each is roughly 150 hours. Budget it explicitly or cut the set size now. |

*Confidence: `verified` confirmed against a primary or peer-reviewed source · `partial` evidence exists but is indirect or contested · `unverified` asserted in v1–v3 with no evidence behind it. Blast radius is what breaks if the assumption is false.*

> **The three that can actually kill this**
>
> **A1, A2 and A3.** Every other row is a cost or a delay; these three change what gets built.
>
> If **A1** fails, the Penda pattern is unavailable to us and the safety net degrades to a second-screen companion — still useful, materially less effective. If **A2** fails, the interview moves from the patient's phone to a nurse-assisted station in the waiting room, which is cheaper to build but consumes staff time and shrinks the net saving. If **A3** holds as found — and it does, the gap is confirmed — we own the drug-safety knowledge base for our formulary subset, which is unglamorous, manual, and non-negotiable.
>
> All three are answerable in the first fortnight, and none needs a model. That ordering is the real content of this section: **the prototype's riskiest unknowns are integration, behaviour and reference data — not intelligence.**

### What this changes in §6

- **Offline-first is now a requirement**, not a nicety — one site in five cannot rely on a live round trip, and one in twelve does not have 24-hour power.
- **The intake surface moves** from patient self-service to nurse-assisted-by-default, with self-service as an opt-in for patients who can. Design for the assisted case first.
- **We do not build an INA-CBG grouper.** We produce accurate ICD-10 and ICD-9-CM codes and hand them to the official one.
- **A drug knowledge base is now an explicit MVP workstream** with an owner, scoped to the molecules the three pathways actually use.
- **Clinician engagement is a primary endpoint**, measured from the first day of shadow mode.

---

<a id="s7"></a>

**§7 — THE MVP**

## Fourteen weeks, three sites, three pathways

Deliberately narrow. The failure mode for this project is not building too little — it is building a general medical assistant that is mediocre at everything and evaluable at nothing.

### Sites

One urban class C, one peri-urban class C, one remote class D. The class D site is the hard case and it should be in from week one, because a system that only works with good connectivity and a full clinical roster is not the system the network needs.

### The always-on layer (all three sites, all visits)

Ambient documentation → SOAP → ICD-10 → FHIR R4 → SATUSEHAT + INA-CBG claim draft. Zero clinical risk, immediate compliance value, and it produces the corpus everything else trains and evaluates on. Expect a real but modest time saving — plan against the NEJM AI figure of ~16 minutes per shift, not vendor claims, and note that in that trial clinicians only used the scribe in a third of eligible visits, so adoption engineering matters as much as model quality.

### Three clinical pathways

| Pathway | Why this one | What the agent does |
|---|---|---|
| `v2 — now first · narrowed v6` Hypertension, chronic follow-up — **alone**. T2DM is V2, combined cardiometabolic V3 (see [SPEC-V1.md](SPEC-V1.md)) | Moved ahead of ARI on review, and the argument is good: it is longitudinal, protocol-dense, measurable, capitation-friendly, and far easier to structure than undifferentiated diagnosis. It also exercises the patient-state layer, which is the part of the architecture we most need to prove. Directly supported by the *Nature* disease-management result. An earlier draft paired it with T2DM; v5 narrowed V1 to hypertension only and this row now matches that decision. | Titration proposals against guideline + formulary; adherence follow-up; escalation triggers; complication screening reminders. |
| Acute respiratory infection, adult & paediatric | Highest volume in the system — J06.9 alone is ~6% of capitation visits. Well-protocolised. Also the pathway where antibiotic over-prescription is most costly, so error reduction is measurable and financially visible. | Async history; red-flag detection (pneumonia, danger signs in children); antibiotic-appropriateness check against PPK and Fornas; patient explanation in local language. |
| TB screening & referral | National priority, ~10% of the global burden, ~32% of cases undetected. **The only pathway where AI beats the locally available human, because there is no radiologist.** `v2` Scoped as an *integration*, not a model build: we procure one of the six WHO-approved CAD products and wire it into the workflow. We are not solving radiology in fourteen weeks. | Procured CAD read on portable X-ray; symptom screen; structured referral packet; notification workflow. |

**Explicitly out of scope for the MVP**

Autonomous prescribing of any kind. Infants under one year. Pregnancy. Psychiatry and self-harm risk. Oncology. Controlled substances. Free-form patient-facing medical advice. Any pathway we cannot adjudicate against a published Indonesian guideline. These are not permanent exclusions — they are the things we will not evaluate properly in fourteen weeks.

### Sequence

**Pipes before brains**

FHIR R4 mapping and SATUSEHAT submission working end-to-end at one site. ASR fine-tuning on recorded consultations (Bahasa first, Javanese/Sundanese in parallel). Grounding corpus ingested and versioned. Deterministic gate v1 — rules, drug safety, Fornas membership — built and unit-tested independently of any model.

**Shadow mode**

Full clinical stack running on live encounters with output visible to *nobody* but the eval harness. This is where the go/no-go data comes from. Adjudication panel of Indonesian physicians scores the disagreements. Red-flag recall measured against the gate thresholds in §9.

**Assist mode, one site**

Traffic light goes live for a single pathway at a single site, with a named accountable clinician and daily review. Expand pathway-by-pathway only when the gates hold. Primary endpoint: blind-adjudicated relative reduction in diagnostic and treatment error, replicating the Penda protocol.

Note the ordering. Documentation and compliance ship before clinical reasoning; the deterministic gate is built before the model is trusted; and nothing reaches a clinician's screen until it has run silently against real patients for four weeks. That order is what makes the Penda result reproducible rather than aspirational.

---

<a id="s8"></a>

**§8 — AUTONOMY**

## The ladder, and the one rung that changes everything

```
 WHAT WE BUILD — LEVEL 2/3            │  WHAT "DIGITAL TWIN" IMPLIES — L5
                                      │
                    ╔═══════════╗     │
  Patient ──▶ Agent ║ CLINICIAN ║     │   Patient ──▶ Agent ══▶ Order
                    ║ STR + SIP ║     │                  │
           proposes ╚═══════════╝     │           decides╎
                          │ signs     │                  ▼
                          ▼           │        ┌ ─ ─ ─ ─ ─ ─ ─ ┐
                       Order          │           Clinician
                                      │        │ audits a       │
                                      │          sample, later
                                      │        └ ─ ─ ─ ─ ─ ─ ─ ┘
 ─────────────────────────────────────┼──────────────────────────────────
 Accountable person exists at the     │  No accountable person at the
 moment of care. Legal under          │  moment of care.
 UU 17/2023. Insurable. Deployable.   │
```

***One edge is the whole argument.** The two systems share their patient interface, their model, their guidelines, and most of their code. The only structural difference is whether the order leaves the building with a signature on it — and that single edge determines licensure, liability, insurability, and whether Kemenkes can regulate the thing at all. Synyi's Dr Hua in Saudi Arabia, the most autonomous clinical deployment in the world today, still sits on the left-hand diagram.*

**Documentation & admin**

Notes, coding, FHIR emission, claim drafts. Clinician edits. No clinical claims. Ships first, pays for itself.

**Safety net — MVP target**

Traffic light on live consultations. Agent flags, clinician decides. This is the Penda level and the level with the strongest evidence base anywhere in the world. Everything in §7 aims here.

**Async intake + drafted plan**

Agent interviews the patient before the visit and hands the doctor a drafted history and candidate plan to countersign. The AMIE and Ant AQ level. Target: month 9–12, after L2 gates hold across all three pathways.

**Supervised autonomy, narrow protocols**

Agent runs the full consultation for a fixed, small set of conditions; a doctor signs before anything is dispensed. The Synyi level. Requires prospective outcome data, an NIE, and a named clinical governance board. 18–24 months, and only for pathways where we have thousands of adjudicated encounters.

**Where the word "twin" finally earns its place**

Past L4 the interesting object decomposes into three, and only one of them is about a doctor.

**Unsupervised — not on the roadmap**

No jurisdiction permits it, no evidence supports it, and no insurer will write it. If someone asks when, the answer is "not on a timeline we can commit to."

### `v3` Three twins, not one

The original brief said "digital twin of a doctor." The defensible version of that idea is not a persona — it is three separate models that meet at the point of decision:

| Layer | What it represents | How it's built | When |
|---|---|---|---|
| Patient twin | What is happening to this person across time — history, medications, lab trends, imaging, prior encounters, adherence. | Structured longitudinal state, versioned. Not ML: a data model. | **v1** — the chronic pathway does not work without it |
| Hospital twin | What this site can actually deliver — stocked formulary, on-site tests, available specialists, referral network, BPJS coverage rules, bed state. | A maintained capability registry per site. Cheap, unglamorous, decisive. | **v1** — it is gate check 9 |
| Physician policy | How a particular good doctor practises: what information they seek, what they consider, what thresholds trigger escalation, what they prescribe, whom they refer. | Learned from that clinician's own adjudicated encounters and override telemetry. Behavioural, never cosmetic. | L4+ — needs thousands of encounters per clinician |

*The third layer is the one that answers the brief's actual ambition, and it is the moat: it lets the network propagate its best clinicians' judgment across all 50 sites. Note what it is *not* — no voice, no likeness, no name on the interface. A decision policy, not a persona.*

### `v3` What to call it

Not "AI doctor" — it sets the wrong expectation with clinicians and the wrong expectation with regulators. Not "digital twin" either, and for a reason §10 makes concrete: that phrase points analysts and procurement teams at organ-simulation and manufacturing-simulation, a different market with different vendors. **"Clinical operator" or "clinical intelligence platform"** describes what it does, survives regulatory scrutiny, and leaves room to grow into the three-twin architecture above without having promised anything unsafe today.

---

<a id="s9"></a>

**§9 — EVALUATION**

## The gates, and the metrics that are allowed to be the headline

We will be asked for an accuracy number. The honest position is that aggregate accuracy is nearly meaningless here and we should refuse to lead with it.

**Five evaluation sets to build**

- **Adjudicated retrospective set** — 1,500 encounters from our own hospitals, independently scored by Indonesian physicians across history, investigations, diagnosis and treatment. This is the Penda protocol and it produces the board-level number.
- **Indonesian pressure suite** — a MedPRESS-style multi-turn adversarial set *written in Bahasa Indonesia*, covering the local pressure patterns (family authority, traditional remedies, antibiotic demand, pharmacy self-medication). Non-optional given §3.
- **Red-flag recall set** — enriched with high-acuity presentations, deliberately over-sampled, because the aggregate datasets under-represent them by an order of magnitude.
- **Task coverage** — a MedHELM-style spread across our actual workflows rather than exam questions, plus a local knowledge floor drawn from UKMPPD-style items and IndoCareer.
- **Formulary and payer conformance** — every generated plan checked against Formularium Nasional and INA-CBG rules. This one has a hard target because it is deterministic.

**Blocking gates before any patient-facing turn**

| Gate | Threshold | Why this number |
|---|---|---|
| Red-flag recall | ≥ 99% | Undertriage is the failure mode that kills. Aggregate F1 does not measure it. |
| Unsafe agreement under 5-turn pressure | < 10% | Best model measured in MedPRESS was 21.9%. We hit this with structural constraint, not prompting. |
| Formularium Nasional violations | 0 | Enforced deterministically at the gate, so anything above zero is a bug, not a model limitation. |
| Unresolvable citations in clinical claims | 0 | Same reason. Glass-box requirement, and what we will show Kemenkes. |
| Note acceptance without major edit | ≥ 80% | Below this, clinicians abandon the tool — the NEJM AI trial saw scribe use in only ~30% of visits. |
| History completeness vs adjudicated gold | ≥ 90% | The largest single block of task-minutes. If the interview misses clinically relevant information, everything downstream is compromised. |
| Appropriate abstention | ≥ 95% | Of cases the gate should have declined on insufficient data, how many did it actually decline? Measures the check most systems omit. |
| Amber/red alert precision | ≥ 70% | Alert fatigue destroys the safety net. Green must genuinely mean silent. |

The headline metric to commit to publicly is the Penda one: **blind-adjudicated relative reduction in diagnostic and treatment error.** It is patient-centred, it is comparable to the best existing evidence, and it is a number a Ministry can act on. If we replicate −16% and −13% across 50 Indonesian hospitals, that is a nationally significant result and by far the strongest thing we could publish.

---

<a id="s10"></a>

**§10 — ECONOMICS**

## The law and the unit economics point the same way

A consultation, end to end — history, retrieval, reasoning, gate checks, note, coding — lands somewhere around 15–25k tokens. On frontier APIs at early-2026 pricing that is roughly $0.05–0.25 per visit depending on model tier; the published spread between providers for the same task runs to two orders of magnitude, and small models are 50–90% cheaper than frontier for open weights of comparable capability on narrow tasks.

Now scale it. Fifty hospitals at a conservative 200 outpatient visits a day is 10,000 visits daily, or roughly **200 million tokens per day** at 20k per visit. The published self-hosting rule of thumb is that on-prem pays off past sustained 50% GPU utilisation, around 10M tokens per day per GPU. We are twenty times over that threshold on day one of full rollout.

> **So the conclusion is over-determined.** GR 28/2024 says PHI must be processed in-country. The unit economics say on-prem inference is cheaper at our volume by a wide margin. Both point at the same architecture: open-weight models on Indonesian infrastructure, with frontier APIs reserved for offline work on de-identified data. We do not have to trade compliance against cost — which is unusual, and worth saying explicitly to the board.

### A warning about the market-size numbers you will be handed

Two vendors sell "Indonesia digital twin in healthcare" market reports. They size the same market in the same year at **USD 10.5M** and **USD 273.5M** respectively — a **26× discrepancy**. When two sizings differ by more than an order of magnitude, neither carries information. Do not put either in a board deck.

They are also sizing the wrong category: both define "digital twin in healthcare" as process, system and whole-body simulation sold into drug discovery, surgical planning and device design, with pharma and device makers as the end users. That is Siemens and Dassault territory, not ours — and it is another reason to drop the phrase entirely.

Build the number bottom-up instead. Fifty hospitals at ~200 outpatient visits a day across ~300 operating days is on the order of **3 million encounters a year**. At $0.30–1.00 of value captured per encounter, this network alone is $0.9–3.0M of annual recurring revenue — which would make our single customer about 6% of the entire market one report projects for 2030. That is not a bullish read on our prospects; it is proof the report measures something else.

The credible anchors are adjacent and better grounded: Indonesian telemedicine at ~USD 405M in 2025 growing to ~USD 977M by 2031, roughly 3,200 hospitals, and the Black Book re-platforming figures in §4.

---

**§10a — VALUE CREATION**

## The EBITDA bridge

A clinical-AI memo that never reaches an EBITDA line is an interesting document, not an investable one. Here is the case in the terms an owner underwrites — and the striking part is that the clinical intelligence is the moat, while the boring layer is the payback.

### Where the money actually leaks

Indonesian hospital revenue does not leak where you would guess. It leaks in coding and claims, and the scale is documented:

- BPJS pending claims reached **Rp 5.92 trillion across 3.69 million cases** by the end of 2024 — nearly triple 2023. `revised v3` That was a peak, not a current state: BPJS has since pushed the national figure down to roughly **Rp 1.35 trillion by April 2026**, so do not quote the 2024 number as though it still stands. The prize survives because private hospitals are not where the improvement landed — ARSSI puts private-hospital pending near **20%** and PERSI around **30%**, and our target is a private group. Treat it as a working-capital release rather than an EBITDA line.
- The five named causes of pending claims are incomplete documentation, coding errors, data mismatch, delays and weak verification. **Three of the five are exactly what an ambient documentation and coding layer addresses.**
- `revised v3 — downgraded` An Indonesian industry analysis claims 30%+ of cases carry unrealised ICD-10 coding optimisation and that routine audits lift reimbursement 10–20%. **This is a single, non-peer-reviewed industry source and has been dropped from the model below.** The load-bearing figures are the peer-reviewed ones: hospitals typically lose **1–5% of revenue** to incomplete coding, and a controlled study of a single documentation intervention — a covering sheet prompting clinicians to record comorbidities — raised revenue **11.7%**. Those bracket our 6% assumption from both sides.

That last point deserves emphasis, because it is the difference between a value-creation thesis and a compliance risk. This is not upcoding. It is coding correctly for care already delivered and documented — severity earned and not claimed, comorbidities present in the note and absent from the claim. The INA-CBG grouper assigns severity from primary diagnosis, secondary diagnoses and procedures; if the secondary diagnoses never reach structured fields, the hospital is paid for a simpler case than it treated.

### The payer is in deficit, and that cuts both ways

`added v4` A verification pass turned up something that belongs at the front of this section rather than buried in it. **BPJS Kesehatan's claim ratio exceeded 100% in 2025** — reported at roughly 108%, against claims paid of about **Rp 201 trillion, up 14.9% on 2024's Rp 175 trillion**, with a reported operating shortfall in the region of Rp 14.6 trillion. Public commentary is now openly asking whether the fund is solvent to 2027. BPJS pays hospitals on the order of Rp 500 billion a day and settles claims in an average of 13.64 days, faster than regulation requires — so this is not a slow-payment story. It is a structural one.

Two figures circulate and they are not the same measure: claims *paid* of ~Rp 201T, and health-service *expenditure* of ~Rp 191.33T (up from Rp 176.11T). Do not add them or use them interchangeably.

The implication for this business case is genuinely two-sided, and an investment committee will ask:

- **Against us.** A payer running above a 100% claim ratio audits harder, tightens verification, and resists tariff growth. Combined with the provincial tariff ceilings in Permenkes 6/2026, the ceiling on "capture more revenue" is lower than a naive model would assume. Any coding uplift must be defensible line by line, because it will be looked at.
- **For us.** That is precisely the environment in which *accurate* coding beats *aggressive* coding. Claim rejection and pending exposure rise when documentation is thin, so the value of getting the secondary diagnoses into structured fields — correctly, with the note behind them — goes up rather than down. And the pending-claims lever in line 2 becomes more about avoiding rejection than about accelerating cash.

The honest framing for the committee: **we are not betting on a generous payer. We are betting that a stressed payer pays accurately-coded claims and challenges everything else.** That is a defensible bet, and it is a different bet from the one the headline Rp 201 trillion implies.

### The bridge

The four-lever EBITDA bridge — coding capture, pending and dispute reduction, clinician throughput, and clinical quality modelled at zero — is set out in full in **DECISION** §8, now as three scenarios rather than a point estimate.

`corrected v5` An earlier draft led with a single **~25% EBITDA expansion** figure. That was more precise than the evidence supports: five inputs are stacked (group revenue, EBITDA margin, BPJS share, coding uplift, flow-through), each individually conservative but multiplied together. The honest presentation is a range — roughly **USD 9M conservative, USD 21M base, USD 29M upside**, or 11–35% expansion — with the **BPJS revenue share named as the dominant sensitivity**. It moves the answer by about a third in either direction and it is the first number to replace with real data.

One reconciliation the earlier draft omitted, and which a reviewer will otherwise attack: our 6% coding uplift is applied to *BPJS revenue*, not group revenue. At a 55% BPJS share that is ~3.3% of total group revenue — inside the peer-reviewed 1–5% band for losses to incomplete coding, and well below the 11.7% recovered in the controlled documentation study. The assumption is conservative; the earlier wording ('sits between the two') compared two different denominators and made it look aggressive.

### Why this ordering is also the safest

Note what the bridge implies about sequencing, and that it agrees with the clinical argument reached independently in §7. The lever with the largest, fastest, most certain return — coding and documentation — carries *no clinical risk at all*. The lever with the deepest moat carries the most, and is modelled at zero. A programme that starts where the money is also starts where the danger isn't. That alignment is rare enough to state explicitly to an investment committee.

It also answers the obvious challenge: if the clinical AI never clears its safety gates, has the money been wasted? No. Lines 1 and 2 stand on documentation, structured capture and claims integrity, and survive the clinical layer being switched off entirely.

---

<a id="s11"></a>

**§11 — PARAMETERS**

## The six calls I made, and what would unmake them

These decisions change the shape of the build. I have taken each rather than leaving it open — a plan contingent on six unanswered questions is not a plan. Each records what I chose, why, and the observation that would overturn it.

1. **Payment model — assume mixed, optimise for claim integrity.**Indonesian hospitals run BPJS case-based payment alongside private and insurance volume; JKN primary care is capitated but hospital outpatient is not. §10a shows claim integrity is the dominant lever under either, so it goes first. *Overturned if:* the group is predominantly capitated primary care, which flips the objective to avoided referral and investigation.
2. **SIMRS — build on Khanza first, one fork.**Resolved in §0. The open-source estate covers the class C/D majority and gives us the source needed for an in-form safety net. Class B sites take the second-screen fallback until a KSO source-code clause can be exercised. *Overturned if:* the group standardised on a single closed commercial SIMRS, in which case the 43% re-platforming wave makes replacing it the better play.
3. **Compute — rent sovereign, don't buy.**Lintasarta's GPU Merdeka runs 8× H100 nodes in-country today, satisfying GR 28/2024 without an eighteen-month hardware lead time. Buy on-prem only once utilisation is proven and steady. *Overturned if:* per-site latency from eastern provinces proves unworkable, pushing small models to the edge.
4. **Evidence — fund the study, scoped to Penda's design.**Not an IRB-grade RCT, which the field itself has not achieved: a quality-improvement study with blinded independent adjudication, which is what produced −16%/−13% and what the NIE file needs. Roughly 150 physician-hours for a 1,500-encounter gold set. *Overturned if:* the budget cannot carry it — in which case say plainly we are building a documentation and claims product, and drop the clinical claims.
5. **Clinical governance — hire before writing code.**One Indonesian-licensed physician (STR + SIP) owning governance, chairing adjudication, signing every pathway expansion. Longest lead time on the team and required under any reading of §1. No condition overturns this one; deferring only makes it later.
6. **Language — Bahasa in v1, Javanese and Sundanese collected from day one.**Ship Bahasa, but start recording consent-covered audio at Javanese-speaking sites immediately, because fine-tuning takes data and data takes months. Zero-shot Javanese ASR is unusable at 89.4% WER against ~13.8% fine-tuned. *Overturned if:* the class D pilot site sits in a strongly non-Bahasa area, making it a v1 blocker rather than a v1.5 feature.

### What genuinely cannot be assumed

Four numbers set the size of the prize and none can be inferred from public data: the group's actual BPJS revenue share, its current coding accuracy and pending-claim rate, whether it employs or contracts its clinicians, and per-site formulary stock. The first three are a two-day finance and operations pull; the fourth is a phone call per site. Until they land, §10a is a model with stated inputs rather than a forecast — which is the honest way to put it to an investment committee regardless.

### What I am most worried about

Not the models. The models are good enough, and §5 shows the task decomposition works out to the number in the brief. What worries me is that the strongest evidence in the field — Penda's −16% — came from an organisation that owned its own clinics, its own EMR, and its own clinical protocols, and could therefore change clinician behaviour as well as ship software. The STAT reporting on that study was blunt about it: the human workflow is the expensive part. If we deploy into 50 hospitals we do not clinically control, with 12 EMR vendors and no authority over how doctors work, we will build something technically excellent that nobody opens.

So my strongest recommendation, beyond anything technical: pick the three pilot sites where we have the most operational control, not the ones with the most patients.

---

<a id="corrections"></a>

**§— CORRECTIONS LOG**

## Everything that changed, and why

This section exists so a reviewer can attack the document efficiently. Every correction below was found by checking a claim against a primary source and finding it wrong or overstated. If you are reviewing this memo, start here — these are the places the argument has already moved once.

| # | Draft | What was claimed | What is actually true | Where |
|---|---|---|---|---|
| 1 | v2 | The task decomposition weighted to ~64% of task-minutes | The table's own numbers weight to **73.3%**. The caption was wrong, not the table. | §5 |
| 2 | v2 | MedGemma 1.5 ships at 4B and 27B | 1.5 is **4B multimodal only**; the 27B variants belong to MedGemma 1. Replaced with a model router — no model name is committed anywhere but the router config. | §2, §6 |
| 3 | v2 | The Penda/Kenya result is RCT-grade | The authors describe it as a **quality-improvement study**. Clinicians were compared with and without access, not randomised. Still the most relevant evidence we have. | §2 |
| 4 | v2 | Autonomous diagnosis is "currently illegal in Indonesia" | There is **no AI-specific health legislation**. It is regulatorily unresolved and uninsurable, which is a different and more accurate claim. | §1, §4 |
| 5 | v2 | PHI can never touch a frontier API | The requirement is **no uncontrolled cross-border processing of identifiable clinical data**. Sovereign in-country deployment stays a live option. | §4 |
| 6 | v2 | TBScreen.AI is a shipping product | It is a **UGM research programme** with a 2026 validation protocol. The six WHO-approved CAD products are what is procurable. | §4 |
| 7 | v2 | AMIE's audio-visual work was missing | Added. 100 scenarios, 300 consultations, 15 patient actors, 10 PCP comparators; beat PCPs at eliciting physical signs. | §2 |
| 8 | v3 | Rp 5.92T of pending claims, presented as current | That is a **2024 peak**; BPJS pushed it to ~Rp 1.35T by April 2026. The private-hospital rates (ARSSI ~20%, PERSI ~30%) carry the argument instead. | §10a |
| 9 | v3 | "10–20% reimbursement uplift from coding audits" | **Single non-peer-reviewed industry source. Dropped from the model.** Replaced with peer-reviewed 1–5% revenue loss and an 11.7% controlled-study uplift, which bracket our 6% assumption. | §10a |
| 10 | **v4** | Permenkes 6/2026 abolished hospital classes A/B/C/D | The shift began with **PP 28/2024** and **Permenkes 11/2025** (3 Oct 2025). Permenkes 6/2026 consolidates 21 regulations and codifies it in Article 12. The commercial consequence holds; the "nobody has noticed this yet" framing does not. | §4 |
| 11 | **v4** | Permenkes 11/2025 is "the SaMD framework" | It is an **omnibus of risk-based licensing standards** for the health subsector (3 Oct 2025), which is why it governs both hospital service standards and device product standards. Device classification traces to **Permenkes 62/2017**. | §4 |
| 12 | **v4** | "HealthBench-JP — 50 Japan-specific scenarios" | The paper is a **gap analysis** of machine-translated HealthBench (5,000 scenarios) using an LLM-as-judge, evaluating GPT-4.1 and LLM-jp-3.1. Not a new benchmark. The real finding is stronger: translation demonstrably leaves systematic gaps. | §4a |
| 13 | **v4** | Ubie: "~47% reduction in document creation time" | Replaced with the figures the company's own 5 Feb 2026 release states — 100 hospitals, Keiju General −42.5% on discharge nursing summaries, Kyushu University Hospital expecting **>¥65M/year revenue improvement**. | §4a |
| 14 | **v4** | Japan's overtime ceilings are 960 / 1,860–1,920 | Level A at **960** is solid. The higher ceilings are reported inconsistently (1,440, 1,860, 1,920 all appear). Now described qualitatively. | §4a |
| 15 | **v4** | The BPJS claim pool was presented without its deficit | BPJS ran a **claim ratio above 100% in 2025** with a reported shortfall around Rp 14.6T. Material to the business case and now stated in §10a. | §10a |
| 16 | **v4** | "61% are buying on claims integration" paraphrased loosely | Verified verbatim and strengthened: **61% prioritise "coding and BPJS/INA-CBG claims workflow automation as the fastest near-term ROI lever."** Source is a vendor press release with no disclosed methodology — now labelled `trade`. | §4 |
| 17 | **v5** | "Yes — but not the version in the brief" | **Wrong and needlessly combative.** The brief asked for 60–70% of what a doctor *does*, which is exactly what we are building. The ambiguity is in the phrase "digital twin," not in the target. Reframed as "yes, and here is what it means." | README, DECISION, §1 |
| 18 | **v5** | In Indonesia the AI "substitutes for a doctor who is not there" | **Contradicts our own thesis.** In both countries the AI takes work off a doctor who is present and signing. What differs is *supervisory depth* — the backup standing behind that doctor. Argument rewritten; the conclusion (higher bar here) survives. | §4a, DECISION |
| 19 | **v5** | 6% coding uplift "sits between" a 1–5% loss band and an 11.7% study | Compared two different denominators. Our 6% is on **BPJS revenue**; at a 55% share that is ~3.3% of group revenue — inside the 1–5% band. Number survives, reasoning corrected. | §10a, DECISION |
| 20 | **v5** | "~25% EBITDA expansion" as a headline figure | Five stacked assumptions presented as one number. Replaced with a **conservative / base / upside range (USD 9M / 21M / 29M)** and BPJS share named as the dominant sensitivity. | §10a, DECISION |
| 21 | **v6** | §7 still listed the first MVP pathway as "hypertension + type 2 diabetes" | Contradicted the v5 decision that narrowed V1 to **hypertension alone** (T2DM is V2). Row corrected to match SPEC-V1 and BUILD. | §7 |
| 22 | **v6** | §6 said the gate "needs eight" checks, then listed nine | Wording left over from before check 9 (executability) was added in v3. Now says nine. | §6 |
| 23 | **v6** | README said "fifteen claims were found wrong or overstated" | The log it points to had twenty rows at the time, and has twenty-three now. Count corrected. | README |

`v6` was an independent review pass by a second model. Beyond the three corrections above it added, rather than corrected: prompt-injection as a named failure mode (SPEC F11), signer identity binding at the signature interrupt (SPEC §5.9), model and prompt versioning in proposal provenance (SPEC §5.6), PRB referral-back (SRB) drafting as a V1 output (SPEC §5.10), the between-visit monitoring loop with its telemonitoring evidence base (SPEC §5.11), and plan-concordance as the measurable "twin fidelity" metric (SPEC §8.2, DECISION §10).

**What has not been verified and cannot be, from public sources:** the group's actual BPJS revenue share; its current coding accuracy and pending-claim rate; whether it employs or contracts clinicians; per-site formulary stock. These set the *size* of the prize, not its existence — see §11.

**Known soft spots a reviewer should push on.** The per-task percentages in §5 are informed estimates, not measurements — no one has timed an Indonesian consultation for this purpose. The connectivity and power figures are measured at *puskesmas* level and applied to hospitals as a proxy. The MedPRESS sycophancy result is a preprint. Every Japanese deployment figure in §4a is vendor- or press-reported. The EBITDA bridge in §10a is a model with stated inputs, not a forecast, and it is most sensitive to the BPJS revenue share, which is assumed.

---

<a id="src"></a>

**§— SOURCES**

## Sources

Confidence varies. Peer-reviewed and preprint sources are cited directly; vendor and trade claims are marked as such in §2 and should be independently verified before any of them enters a board deck. Where two sources disagreed — notably MedGemma's MedQA score and Indonesia's physician ratio — both figures are given in the text.

1. [AMIE real-world feasibility study at BIDMC](https://research.google/blog/exploring-the-feasibility-of-conversational-diagnostic-ai-in-a-real-world-clinical-study/) — Google Research, Mar 2026; [preprint](https://arxiv.org/pdf/2603.08448)
2. [Towards conversational AI for disease management](https://www.nature.com/articles/s41586-026-10764-5) — *Nature*, 17 Jun 2026
3. [Advancing AMIE towards expert-level audio-visual clinical consultations](https://research.google/blog/advancing-amie-towards-expert-level-audio-visual-clinical-consultations/) — Google Research, 11 Aug 2026
4. [Towards conversational diagnostic AI](https://www.nature.com/articles/s41586-025-08866-7) — *Nature*, 2025
5. [AI-based Clinical Decision Support for Primary Care: A Real-World Study](https://arxiv.org/abs/2507.16947) — Penda Health × OpenAI
6. [Why the human workflow is health AI's biggest, costliest problem](https://www.statnews.com/2025/10/01/penda-health-open-ai-safety-net-study-kenya-artificial-intelligence/) — STAT News
7. [MedPRESS: patient-pressure-induced medical sycophancy](https://arxiv.org/abs/2608.02520) — Aug 2026
8. [HealthBench Professional](https://arxiv.org/html/2604.27470) — OpenAI, Apr 2026
9. [HealthBench](https://openai.com/index/healthbench/) — OpenAI
10. [Ambient AI Scribes in Clinical Practice: A Randomized Trial](https://ai.nejm.org/doi/abs/10.1056/AIoa2501000) — *NEJM AI*
11. [MedGemma 1.5 model card](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card) — Google, Jan 2026
12. [MedHELM: holistic evaluation of LLMs for medical tasks](https://pubmed.ncbi.nlm.nih.gov/41559415/)
13. [AI models for predicting triage in emergency departments](https://medinform.jmir.org/2026/1/e83318/PDF) — JMIR Medical Informatics, 2026
14. [AI-CDSS for teleconsultations in eSanjeevani, India](https://www.medrxiv.org/content/10.1101/2025.11.22.25340800v1)
15. [Synyi AI's Dr Hua clinic, Al-Ahsa](https://www.bloomberg.com/news/articles/2025-05-15/chinese-startup-trials-first-ai-doctor-clinic-in-saudi-arabia) — Bloomberg
16. [Ant Group's AQ for Doctor](https://technode.global/2026/08/12/chinas-ant-group-upgrades-physician-platform-into-ai-workstation-aq-for-doctor-with-300000-verified-doctors/) — TNGlobal, Aug 2026
17. [The regulatory pulse of Indonesian healthcare AI](https://www.hbtlaw.com/insights/2026-03/the-regulatory-pulse-of-indonesian-healthcare-ai) — HBT, Mar 2026
18. [Indonesia UU PDP and AI data protection](https://www.pertamapartners.com/insights/indonesia-pdp-law-uu-pdp-ai-data-protection) — Pertama Partners
19. [Data Protection & Privacy 2026: Indonesia](https://practiceguides.chambers.com/practice-guides/data-protection-privacy-2026/indonesia/trends-and-developments) — Chambers
20. [Indonesia medical device regulations: IDAK, CDAKB, NIE](https://omcmedical.com/blog/indonesia-medical-device-regulations) — incl. Permenkes 11/2025
21. [Registering medical device software (SaMD) in Indonesia](https://insightof.id/registering-medical-device-software-in-indonesia/)
22. [Blueprint for Digital Health Transformation Strategy](https://dto.kemkes.go.id/ENG-Blueprint-for-Digital-Health-Transformation-Strategy-Indonesia%202024.pdf) — DTO Kemenkes
23. [FHIR-based interoperability design in Indonesia](https://pmc.ncbi.nlm.nih.gov/articles/PMC12036547/) — JMIR Formative Research
24. [SATUSEHAT developer portal](https://satusehat.kemkes.go.id/platform/sign-up) — OAuth2 onboarding and organisation registration
25. [Assessing internet quality across public health centers in Indonesia](https://www.sciencedirect.com/org/science/article/pii/S2291969425001991) — cross-sectional study; connectivity and electricity figures
26. [Kepmenkes HK.01.07/MENKES/1199/2025 — Formularium Nasional](https://farmalkes.kemkes.go.id/en/unduh/keputusan-menteri-kesehatan-republik-indonesia-nomor-hk-01-07-menkes-1199-2025-tentang-formularium-nasional/)
27. [e-Fornas portal](https://e-fornas.kemkes.go.id/) — Kemenkes
28. [BPOM drug registration database](https://www.badanpom.id/) — product authorisation only, not clinical pharmacology
29. [Lintasarta GPU Merdeka sovereign AI cloud](https://www.datacenterdynamics.com/en/news/indosats-lintasarta-launches-ai-cloud-gpu-merdeka-in-indonesia/) — DCD
30. [Radiation medical device registration](https://productregistrationindonesia.com/services/radiation-medical-device-registration-in-indonesia/) — BAPETEN, IDAK, CDAKB requirements
31. [Mapping telemedicine in Indonesia](https://thinkwell.global/wp-content/uploads/2025/03/Telemedicine_in_Indonesia-FINAL-1.pdf) — ThinkWell
32. [SIMRS Khanza source repository](https://github.com/mas-elkhanza/SIMRS-Khanza) — open-source Indonesian HIS, incl. `src/bridging/` BPJS PCare, Siranap and Dukcapil modules
33. [Yayasan SIMRS Khanza Indonesia (YASKI)](https://www.yaski.or.id/) — the foundation behind Khanza
34. [Hermina Hospitals](https://en.wikipedia.org/wiki/Hermina_Hospitals) — 52 hospitals, 63 cities, 17 provinces (Dec 2024)
35. [Siloam Hospitals valuation multiples](https://multiples.vc/public-comps/siloam-hospitals-valuation-multiples) — 24% EBITDA margin, ~4,000 beds, 65% occupancy
36. [ICD-10 coding optimisation for BPJS claims](https://medminutes.io/blog/optimasi-koding-icd10-bpjs/) — 30%+ of cases carry unrealised optimisation; 10–20% uplift from audits
37. [Post-claim BPJS verification, pending and dispute](https://medminutes.io/blog/pasca-klaim-bpjs-rumah-sakit-panduan-lengkap-2026/) — Rp 5.92T pending across 3.69M cases; iDRG dual-rate transition
38. [Indonesian hospital EHR modernisation and replacement intent](https://www.newswire.com/news/indonesia-hospitals-step-up-ehr-modernization-momentum-grows-for-core-system) — Black Book
39. [Indonesia health care system profile 2026](https://www.commonwealthfund.org/sites/default/files/2026-05/2026_Country-Profiles_Indonesia.pdf) — Commonwealth Fund
40. [Indonesian National Health Insurance longitudinal sample data](https://link.springer.com/article/10.1186/s12913-025-13756-9) — BMC Health Services Research
41. [WHO approves six CAD products for TB on chest X-ray](https://www.who.int/news/item/11-06-2025-who-approves-six-software-products-for-computer-aided-detection-of-tb-on-chest-x-ray) — Jun 2025
42. [AI for TB screening: from evidence to policy and implementation](https://www.mdpi.com/2075-4418/16/8/1127)
43. [Specialist doctor shortage in Indonesia](https://ugm.ac.id/en/news/primary-care-empowerment-urged-amid-specialist-doctor-shortage-in-indonesia/) — UGM
44. [LLM transcription and summarisation into ePuskesmas](https://arxiv.org/pdf/2409.17054) — Indonesian proof-of-concept
45. [PNPK 2026 collection](https://kemkes.go.id/id/media/list/pedoman/pedoman-nasional-pelayanan-kedokteran-pnpk/kumpulan-pnpk-tahun-2026) — Kemenkes
46. [FDA's Jan 2026 CDS guidance and Aug 2026 generative-AI discussion paper](https://www.nixonlawgroup.com/resources/fda-relaxes-clinical-decision-support-and-general-wellness-guidance-what-it-means-for-generative-ai-and-consumer-wearables) — useful precedent for the glass-box framing
47. [Protecting physicians from AI impostors](https://www.thinkglobalhealth.org/article/protecting-physicians-from-ai-impostors) — Think Global Health
48. [Personal.ai — "Your Doctor's Digital Twin"](https://www.personal.ai/pi-ai/your-doctors-digital-twin) — marketing page; no deployments, validation or regulatory statement disclosed
49. [Indonesia Digital Twin in Healthcare Market](https://www.nextmsc.com/report/indonesia-digital-twin-in-healthcare-market-ic3902) — Next Move Strategy Consulting, May 2026 `not usable`
50. [Indonesia Digital Twin Healthcare Market](https://mobilityforesights.com/product/indonesia-digital-twin-healthcare-market) — Mobility Foresights, Aug 2025 `not usable`
51. [TBScreen.AI development programme](https://centertropmed-ugm.org/project/tbscreen-ai/) — Center for Tropical Medicine, UGM
52. [Life Sciences 2026: Indonesia](https://practiceguides.chambers.com/practice-guides/life-sciences-2026/indonesia) — Chambers, on health-data hosting conditions
53. [Health Minister on the 93,200 GP shortfall projected for 2032](https://tirto.id/menkes-sebut-indonesia-kekurangan-93200-dokter-umum-pada-2032-hxv6) — Tirto, Jun 2026
54. [Permenkes No. 6 Tahun 2026 tentang Rumah Sakit](https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-6-tahun-2026) — Kemenkes JDIH; enacted 4 Jun 2026, promulgated 12 Jun 2026
55. [Catatan Kaki Permenkes No. 6/2026](https://persijatim.id/2026/07/20/catatan-kaki-permenkes-nomor-6-tahun-2026/) — PERSI Jawa Timur, on the evidencing burden and Article 74
56. [From class-based to capability-based hospitals under Permenkes 6/2026](https://mudanews.com/lingkungan-kesehatan/2026/06/16/pergeseran-paradigma-pengelolaan-rumah-sakit-dalam-permenkes-nomor-6-tahun-2026-dari-hospital-class-based-menuju-capability-based-hospital/)
57. [Kemenkes national conference on safe, fair and accountable health AI](https://keslan.kemkes.go.id/read/3798/kemenkes-dorong-pengembangan-ekosistem-ai-kesehatan-yang-aman-adil-dan-bertanggung-jawab) — 8–9 Jun 2026
58. [Japan's 2024 physician work-style reform: overtime caps and task redistribution](https://www.medical-jpn.jp/hub/en-gb/blog/industry-insights/upcoming-work-style-reforms-for-doctors-in-japan.html)
59. [Impact of Japan's 2024 physician work-style reform on working hours](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12346560/) — incl. the MHLW Dec 2024 rural-dispatch survey
60. [Overview of task-shifting guidelines in Japan](https://link.springer.com/article/10.1007/s11604-025-01774-w) — *Japanese Journal of Radiology*
61. [High prices squeeze Japanese hospitals — ~60% in the red](https://asianews.network/high-prices-squeeze-hospitals-in-japan-60-now-in-the-red/)
62. [Japanese regulation and approval of medical AI as SaMD: current status and emerging challenges](https://www.jstage.jst.go.jp/article/ghm/8/3/8_2026.01052/_article/-char/en)
63. [PMDA — Software as a Medical Device](https://www.pmda.go.jp/english/review-services/reviews/0009.html); core guidance updated 5 Jun 2026
64. [Regulatory transparency in AI-based radiology software: PMDA-approved SaMD products](https://link.springer.com/article/10.1007/s11604-025-01942-y) — ~40 AI-enabled of 151 approvals
65. [Filling in the clinical gaps: HealthBench for the Japanese medical system](https://arxiv.org/abs/2509.17444) — a gap analysis of machine-translated HealthBench, **not** a new benchmark (corrections log #12)
66. [JMedBench: evaluating Japanese biomedical LLMs](https://arxiv.org/pdf/2409.13317)
67. [NTT tsuzumi 2 — domestic Japanese LLM](https://group.ntt/en/newsrelease/2025/10/20/251020a.html) — 20 Oct 2025
68. [Ubie generative AI deployed to 100 hospitals including 10+ university hospitals](https://prtimes.jp/main/html/rd/p/000000198.000048083.html) `vendor`
69. [Fujitsu Japan and JCHO Osaka Hospital generative-AI project](https://global.fujitsu/en-global/subsidiaries/fjj/news/press-releases/2026/0219-01) — agreement 13 Feb 2026, live Jun 2026
70. [EUCALIA and Hippocratic AI — non-diagnostic Japanese patient-facing agent](https://www.businesswire.com/news/home/20250507549014/en/EUCALIA-Inc.-and-Hippocratic-AI-Partner-to-Bring-Worlds-First-Non-Diagnostic-Patient-Facing-Japanese-Generative-AI-Healthcare-Agent-to-Market) — May 2025
71. [Japan's Electronic Medical Record Information Sharing Service](https://www.phchd.com/jp/medicom/park/tech/ehr-information) — HL7 FHIR, three documents and six information sets
72. [FY2026 Japanese fee revision — the Electronic Clinical Information Sharing System Setup Addition](https://med-cpa.jp/hoshu-15/)
73. [Permenkes No. 11 Tahun 2025 — Standar Kegiatan Usaha dan Standar Produk/Jasa, Perizinan Berusaha Berbasis Risiko Subsektor Kesehatan](https://peraturan.go.id/id/permenkes-no-11-tahun-2025) — 3 Oct 2025; revokes Permenkes 26/2018
74. [Permenkes 6/2026 and hospital licensing](https://siplawfirm.id/resources/permenkes-6-2026-perizinan-rumah-sakit) — SIP Law Firm, on Articles 6–10
75. [From class-based to capability-based hospitals](https://persijatim.id/2025/06/20/perubahan-klasifikasi-rumah-sakit-dari-klasifikasi-kelas-rumah-sakit-abcd-ke-klasifikasi-jenis-pelayanan-rumah-sakit-meliputi-pelayanan-paripurna-utama-madya-dan-dasar/) — PERSI JATIM, Jun 2025; evidence the change predates Permenkes 6/2026
76. [Klaim BPJS Kesehatan 2025 Rp 201 T, naik 14,9 persen dari 2024](https://www.antaranews.com/berita/5297890/klaim-bpjs-kesehatan-2025-rp-201-t-naik-149-persen-dari-2024) — ANTARA
77. [BPJS Kesehatan akui rasio klaim JKN tembus di atas 100% pada 2025](https://keuangan.kontan.co.id/news/bpjs-kesehatan-akui-rasio-klaim-jkn-tembus-di-atas-100-pada-2025) — Kontan
78. [BPJS Kesehatan: pengeluaran layanan 2025 Rp 191,33 triliun](https://nasional.kompas.com/read/2026/07/02/19451181/bpjs-kesehatan-pengeluaran-layanan-2025-tembus-rp-19133-triliun-rasio-klaim) — Kompas; note this is a different measure from claims paid
79. [Transisi INA-CBG ke iDRG 2026](https://medminutes.io/blog/transisi-ina-cbg-idrg-rumah-sakit-2026/) — severity levels 3→4, CC/MCC documentation; no national go-live as of Apr 2026
80. [15% of doctors put in over 960 hours of overtime, health ministry survey finds](https://www.japantimes.co.jp/news/2026/07/14/japan/society/hospital-doctors-overtime/) — The Japan Times, Jul 2026
81. `v6` [Panduan Lengkap Program Rujuk Balik (PRB) untuk Rumah Sakit 2026](https://medminutes.io/blog/panduan-lengkap-program-rujuk-balik-prb-rumah-sakit-2026/) — the SRB workflow and BPJS's 3B criteria (benar diagnosa, benar stabil, benar obat); trade source, mechanism corroborated by BPJS regional statements
82. `v6` [Effect of telemonitoring and home blood pressure monitoring on blood pressure reduction in hypertensive adults: a network meta-analysis](https://pubmed.ncbi.nlm.nih.gov/40156340/) — −3.69 mmHg SBP vs usual care, 24 RCTs
83. `v6` [Impact of home blood pressure telemonitoring and blood pressure control: a meta-analysis of randomized controlled studies](https://pubmed.ncbi.nlm.nih.gov/21654858/) — −5.64 mmHg office SBP; with the network meta-analysis, brackets the 3.7–5.6 mmHg range quoted in SPEC-V1 §5.11

---

---

*Internal research memo · Office of the CTO · evidence current to 29 August 2026.*
