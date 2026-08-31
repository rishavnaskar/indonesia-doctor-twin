# Can this work?

**An AI clinician for a 50-hospital Indonesian network: the case, the limits, and what we'd build.**

*Read this one, it's about twelve minutes. [RESEARCH.md](RESEARCH.md) has the evidence and the sources behind every number, plus a log of every correction made along the way. [BUILD.md](BUILD.md) has the implementation plan.*

---

## 1. The idea

A company runs 50+ hospitals across Indonesia. Most are small, most are outside Java, and most cannot get or keep good doctors. The brief: build a digital twin of a doctor that does 60–70% of the job.

- Indonesia sits at roughly **0.45–0.5 doctors per 1,000 people**, against a WHO reference of 1.0.
- In June 2026 the Health Minister put the shortfall at **93,200 general practitioners by 2032**, i.e. 255,420 needed against 162,220 available.
- **About four in five** Indonesian general hospitals sit in the bottom two capability tiers: basic services, two to four specialties, no radiologist on site.
- The problem is not only *how many* doctors. It is *where the expertise sits*, and *how much doctor time goes on paperwork*.

---

## 2. The verdict

> ### Yes, and here is what it means.
>
> The brief asks for a system that does 60–70% of what a doctor does. That is the right target and it is achievable: the history, the summary, the suggested diagnosis, the treatment plan, the prescription, the notes, the codes, the follow-up. The doctor stops writing everything from scratch.
>
> What it cannot mean is 60–70% of what a doctor **decides**. Nobody has built that. The most autonomous clinical deployment running anywhere today, an AI-run clinic in Saudi Arabia, still has a human doctor sign every plan before the patient leaves.
>
> The outcome the hospital wanted is unchanged: more patients per doctor, fewer mistakes. Keeping the decision with the doctor is what makes it legal, insurable and deployable this year rather than a research programme.

The phrase "digital twin" is ambiguous, and the ambiguity is expensive. The two readings need near-identical software but produce quite different companies:

| Reading | Verdict |
|---|---|
| 60–70% of a doctor's **judgment**, i.e. AI decides and human spot-checks | Not viable. Nobody has done it. Not insurable. Not defensible to a regulator. |
| 60–70% of a doctor's **work**, i.e. AI drafts everything and the doctor decides | Buildable today. Same throughput outcome for the hospital. **This is what we build.** |

**One more thing: drop the phrase "digital twin"**, at least commercially. Market analysts use it for organ and manufacturing simulation, which points investors and procurement teams at a different category with different vendors. I'd call it a **clinical operator**.

But it's worth taking the phrase seriously as engineering, because the brief's other instruction (*this is not a chatbot*) is one we satisfy by construction. The system is a **state machine over a longitudinal patient model** rather than a conversation: patient state that keeps syncing between visits, a decision policy whose fidelity gets *measured* (of the decisions good doctors actually made, what fraction does the draft match, per SPEC-V1 §8.2), and a replayable record of what the system saw when it spoke. Synchronised state, measured fidelity, replayable counterfactuals: that's roughly what "twin" means in the engineering fields that use the word rigorously. Chat appears in exactly one place, and it's a bounded interview with no clinical voice.

---

## 3. The line everything sits on

```
        AI DRAFTS            │ SIGNATURE │        DOCTOR DECIDES
                             │           │
  suggests a diagnosis       │           │  accepts, edits or bins it
  writes the prescription    │           │  nothing leaves the room
  proposes the plan          │           │  until they do
  fills in the codes         │           │  system records what they did
```

"AI suggests a diagnosis" is fine. "AI makes the diagnosis" is not. That one word is the entire legal position, and it is cheap to enforce in software rather than in a policy document.

**Help flows in two directions, and it is worth separating them because they get confused.**

| | What it does | Example |
|---|---|---|
| **Drafting** (forward) | The AI writes first, the doctor edits. Saves time. | Draft note, draft prescription, suggested diagnosis, draft codes |
| **Safety net** (backward) | The doctor decides first, the AI checks it and speaks only if something looks wrong. Catches errors. | Dose is 10× too high · drug the patient is allergic to · red flag in the history nobody actioned |

The safety net is the direction with the published evidence behind it: Kenya's −16% came from a traffic light that sat quietly next to a clinician and went amber or red when the plan looked unsafe. Green means silent. Most of the time the doctor never sees it, and that silence is exactly what keeps the amber and red signals worth reading.

Drafting is where the time saving lives. The safety net is where the error reduction lives. We build both, and they are not the same feature.

---

## 4. What the evidence actually supports

| Where | What happened | How much weight it carries |
|---|---|---|
| **Kenya**, 15 clinics, 39,849 visits | An AI safety net cut diagnostic errors **16%** and treatment errors **13%**, rated by independent physicians | Strongest real-world evidence there is. A quality-improvement study, not a randomised trial. |
| **Google AMIE**, 100 real patients | Right diagnosis in the AI's shortlist **90%** of the time; zero safety interventions needed | Small, one US site. Lost to human doctors on plan *practicality*. |
| **Google AMIE (video)**, 300 consultations | Matched physicians overall, **beat them** at eliciting physical signs | Simulated patients, not real ones |
| **Ambient scribes**, 238 physicians, randomised | ~16 minutes saved per shift; used in only **a third** of eligible visits | Real, and a warning about adoption |
| **HealthBench Professional** | Frontier models score **59.0** on clinician tasks against physicians' **43.7** | Models now beat doctors at clinical writing |

Kenya matters most. Same resource constraints, same clinician mix, cheap Android tablets, unreliable connectivity. Not America's problem set.

**And the counter-evidence, which shapes the product more than any of the above.** A 2026 study ran 600 five-turn medical conversations across 20 model configurations: push back on a medical AI a few times and about **half fold and agree with you**, even when you are wrong. Symptom triage was the worst category of all, with models flipping at a mean of turn 1.8. Anti-sycophancy prompting bought only 14 percentage points. This is why patients never chat freely with our system about symptoms; they answer a bounded interview, and every clinical claim goes through deterministic checks before a human sees it.

---

## 5. Someone is already building this, in Japan

Which is useful, because it moves the question from "can this work" to "what carries over."

**Japan proved the reframe by accident.** In April 2024 Japan capped physician overtime at 960 hours a year. Hospitals could no longer fix capacity by working people harder, so the Health Ministry published an official list of jobs to take off doctors: the first round of questions, explaining procedures, medication guidance, filling in documents on the doctor's behalf. That list is our feature list. A G7 health ministry reached the same answer we did, from the opposite direction, and wrote it into policy. A further ministry survey reported in July 2026 found roughly 15% of hospital doctors still over the cap, so the pressure hasn't resolved itself.

**And everyone selling into that market entered through the same door we chose.** Ubie does pre-visit questionnaires and document drafting, across 100 hospitals including 10+ university hospitals as of January 2026, with one hospital measuring 42.5% off discharge nursing summary time and Kyushu University Hospital expecting over ¥65M a year of revenue improvement. Fujitsu signed with a large Osaka hospital in February 2026 for discharge summaries and nursing handovers, live in June. Hippocratic AI's Japanese launch put the word **non-diagnostic** in its own headline. Three well-funded independent teams; none of them selling a diagnosing doctor.

**Four things don't survive the flight south**, and saying so is the point:

| | Japan | Indonesia |
|---|---|---|
| **The sale** | Survival. Around 60% of hospitals are losing money | Growth. Private groups here are profitable |
| **What drives adoption** | The fee schedule literally pays hospitals to go digital | Nothing equivalent. It's an internal mandate or it doesn't happen |
| **Regulator** | PMDA has an AI pathway, ~40 approved AI devices, a fast track | No AI-specific pathway. The ministry was still holding a governance conference in June 2026 |
| **Testing it** | Japanese researchers measured what breaks when you translate an American benchmark, and a Japanese-native model failed on clinical completeness | Nothing comparable exists in Bahasa Indonesia. We would have to build it |

**One thing runs the other way, and nobody expects it: on plumbing, Indonesia is ahead.** Japan's national data exchange only reaches full operation around this winter and its hospital systems are closed vendor estates. SATUSEHAT is already mandatory with sanctions live, and the hospital system most small Indonesian hospitals run is open source. Japan had to ask permission. We have the source code.

> ### The safety bar goes up here, not down
>
> To be clear about what we are and are not claiming: in both countries the AI takes work off a doctor who is present and signing. We are not covering for an absent doctor. What differs is **how much clinical backup stands behind that doctor.**
>
> A Japanese hospital doctor working through an AI draft sits inside a dense support structure: colleagues to ask, a radiologist on site, specialists down the corridor. In a smaller Indonesian hospital the same draft is reviewed by a general practitioner who may have no radiologist, no on-site specialist and nobody to check with before the patient leaves.
>
> Same software, same signature, far thinner review capacity around it. So a bad output is less likely to be caught by somebody else, which is why the checking parts get built first and tested hardest, and why the gate refuses rather than guesses when it isn't sure.

---

## 6. What we'd build: 30 features

Risk here means how much damage a bad output does before a human catches it, rather than how hard it is to build.

| Stage | Features | Clinical risk |
|---|---|---|
| **Before the visit** | History interview · patient summary · care-gap flags · queue priority | low |
| **In consultation** | Suggested diagnosis · treatment plan · prescription draft · test suggestions · red-flag alerts · guideline lookup · notes written for you | **high** on the first three |
| **Wrapping up** | Patient instructions · referral letter · referral screening · sick notes · billing codes · claim check · PRB referral-back draft | none–low |
| **After discharge** | Result triage · follow-up calls · dose adjustment · discharge summary | mixed |
| **Behind the scenes** | Coding sweep · documentation queries · quality dashboard · junior second opinion · TB X-ray screening | none–medium |
| **Compliance** | Capability evidence pack · all-operations reporting · cost-per-case against the tariff ceiling · accreditation evidence | none |

**Build order is the inverse of glamour.** The zero-risk paperwork features ship first, because they pay for the company. The high-risk clinical features ship last, once we can prove they're safe. We don't build 30 things at once.

Two of these deserve a sentence because nobody else will build them. The **PRB referral-back draft**: when a chronic patient meets BPJS's own stability checklist, the system drafts the referral-back letter that moves them to primary care, which frees the scarcest resource in the network (specialist time) and does it with the payer's blessing. And the **between-visit loop**: home BP readings and refill signals flowing into the patient state through structured, button-driven check-ins rather than open chat, with meta-analyses putting the effect at 3.7–5.6 mmHg of additional systolic reduction. Both are specified in SPEC-V1 §5.10–5.11.

**The useful accident:** the safest features to build are also the most profitable. Notes and codes touch no clinical decision. If the diagnosis suggestions never clear safety testing, the money side still works, which is worth saying out loud to whoever writes the cheque.

---

## 7. What we deliberately don't build

- **The AI committing to a diagnosis.** It suggests, ranks and explains. It's never the one who decided, since that's who gets sued and who the regulator talks to. Permanent.
- **Unsigned prescriptions reaching the pharmacy.** Enforced in software, not in a policy document.
- **Open-ended patient chat about symptoms.** See the sycophancy evidence in §4. The patient talks to an *interviewer*, not an *advisor*.
- **Anything we can't trace to an Indonesian guideline.** No source, no answer.
- **Babies, pregnancy, mental health, cancer, controlled drugs.** Not forever, just not first, because we can't test them properly in three months.
- **Our own TB imaging model.** WHO has approved six. We buy one.
- **An INA-CBG grouper.** The government's grouper prices the claim. We produce accurate codes and feed it.

---

## 8. The business case

> **A modelled EBITDA impact of USD 9–29M within two years on a USD 420M / USD 84M asset (roughly 11–35% expansion) before the clinical AI books a rupiah.**

**Read that as a range, not a number.** Five inputs are stacked here (group revenue, EBITDA margin, BPJS share, coding uplift and flow-through) and each is individually conservative, but they multiply. A single headline figure would imply a precision we don't have. The base case lands near USD 21M (~25%) and the conservative case near USD 9M. The honest position is that **the BPJS revenue share alone moves the answer by roughly a third in either direction**, and it's the first number I'd replace with real data.

| Scenario | BPJS share | Coding uplift | Throughput gain | EBITDA impact |
|---|---|---|---|---|
| Conservative | 40% | 4% | 6% | **~USD 9M** (~11%) |
| Base | 55% | 6% | 12% | **~USD 21M** (~25%) |
| Upside | 70% | 8% | 15% | **~USD 29M** (~35%) |

### Where the money is

| Lever | Model | EBITDA | When |
|---|---|---|---|
| **Coding capture** | 6% uplift on BPJS revenue. ~90% flow-through, since the care was already delivered | **~USD 12.5M** | Months 4–12 |
| **Pending & disputes** | Cut held claims 40% by fixing documentation at source | ~USD 2M + ~USD 7M working capital | Months 6–18 |
| **Clinician throughput** | 12% more outpatient capacity, net of added nurse time | ~USD 7M | Months 9–24 |
| **Clinical quality** | Kenya's −16% / −13% | **Modelled at zero** | Year 3+ |
| **Compliance reporting** | Permenkes 6/2026 capability evidence and Article 74 returns | **Modelled at zero**, since it's the wedge rather than the return | Months 6–18 |

Build cost USD 3.5–5M over 18 months plus ~USD 0.6M a year of infrastructure. Coding capture alone repays it inside a year.

### Why coding, specifically

**First, what "coding" means here.** After every visit, someone has to translate what happened into standard codes: ICD-10 for diagnoses, ICD-9-CM for procedures. Those codes, not the doctor's written notes, are what BPJS actually pays against. A government grouper reads the primary diagnosis, the secondary diagnoses and the procedures, and assigns the case to one of 1,075 payment groups at one of three severity levels. **The hospital is paid for the codes, not for the care.**

So when a doctor writes "patient also has chronic kidney disease" in free text and nobody codes it, the grouper never sees it, the case is priced as simpler than it was, and the hospital is underpaid for work it already did. That is the leak.

**This is not upcoding.** It is billing for diagnoses already written in the notes.

**Is 6% defensible?** Peer-reviewed work puts typical losses from incomplete coding at **1–5% of total hospital revenue**; a controlled study of one intervention (a covering sheet prompting clinicians to record comorbidities) recovered **11.7%**. Our 6% is applied to *BPJS revenue only*, which we model at 55% of the group, so it works out at roughly **3.3% of total group revenue**, which is inside the documented loss band and well below the intervention study. Stated as "6%" it sounds aggressive. Reconciled to the same denominator as the evidence, it's fairly conservative.

### The payer is in deficit, and you should know that before you read the table above

**BPJS paid out about Rp 201 trillion in claims in 2025, up 14.9% on 2024's Rp 175 trillion.** That is the pool, and it is growing. But the claim ratio ran **above 100%** (reported around 108%) with a shortfall in the region of Rp 14.6 trillion, and public commentary is now openly questioning solvency to 2027.

That cuts both ways, and an investment committee will ask:

- **Against us.** A payer above a 100% claim ratio audits harder and resists tariff growth. Any coding uplift has to be defensible line by line, because it will be looked at.
- **For us.** That is exactly the environment where *accurate* coding beats *aggressive* coding. Rejection and pending exposure rise when documentation is thin, so getting the secondary diagnoses into structured fields correctly, with the note behind them, is worth more rather than less.

The honest framing: **we are not betting on a generous payer. We are betting that a stressed payer pays accurately-coded claims and challenges everything else.**

### One correction worth carrying

Held claims spiked to Rp 5.92T across 3.69M cases in 2024, nearly triple 2023, but BPJS pushed that down to roughly **Rp 1.35T by April 2026**. Don't quote the 2024 figure as current. The prize survives because private hospitals are not where the improvement landed: ARSSI puts private-hospital pending near **20%** and PERSI around **30%**, and our target is a private group. Treat it as working capital, not EBITDA.

**And the clinical AI is the moat, not the payback.** Budget it accordingly.

---

## 9. Why now

- **SATUSEHAT compliance is mandatory** and 1,200+ hospitals have been flagged. Sanctions are live.
- **The buying window is open and the buying criterion is ours.** A Black Book market survey published 4 February 2026 found 80% of Indonesian hospitals active in at least one EHR initiative, **43% intending to replace or materially re-platform their core SIMRS/EHR within 24 months**, and, the line that matters, **61% prioritising "coding and BPJS/INA-CBG claims workflow automation as the fastest near-term ROI lever."** That is our phase 1, named as the market's own top priority. A further 58% report they have no dedicated interoperability function, meaning they cannot do the FHIR work themselves. *(Vendor market research, with no sample size or methodology disclosed, so treat it as directional rather than as a measurement.)*
- **Hospital regulation was consolidated in June 2026.** Permenkes 6/2026 rolls 21 regulations into one, codifies capability-based classification assessed *per service group*, requires reporting of all hospital operations to the national system (Article 74), and makes accreditation itself a sanction. Two-year transition. *Note: the classification shift didn't start here. It began with PP 28/2024 and Permenkes 11/2025. What changed in June is that it became consolidated, enforceable and dated.*
- **The price lever just closed.** The same regulation puts hospitals under a national tariff framework with ceilings set by provincial governors. If you can't raise prices, revenue growth has to come from coding what you actually did and seeing more patients. That is our entire pitch, made compulsory by law.
- **iDRG is coming**, and it raises severity levels from three to four with more demanding complication and comorbidity documentation. Announced for October 2025, still no national go-live as of April 2026, so I wouldn't build the plan around the date. But comorbidity capture matters more under iDRG than today, and hospitals coding by hand will struggle through the transition.
- **Sovereign GPU exists now.** Lintasarta's GPU Merdeka runs H100 nodes in-country, so the data-residency law is satisfiable without an 18-month hardware order.
- **Health AI governance is being written now, not later.** Kemenkes ran a national conference on safe and accountable health AI on 8–9 June 2026, with informed-consent standards on the agenda. Being in the room while rules are drafted is worth more than complying with rules already written.

---

## 10. What's defensible

Three things compound, and a competitor can't copy them:

1. **Longitudinal patient state** across 50 hospitals, which is probably the only complete picture of these patients that exists anywhere.
2. **Hospital capability model** per site: what's actually stocked, what tests run, which specialists exist. This is why our plans are executable and a generic tool's aren't; AMIE's *one* loss to human doctors was on plan practicality. **And the regulator now requires the same object**: Permenkes 6/2026 grades capability per service group on diagnoses, procedures, competencies, facilities and equipment, and the hospital association's own reading is that naming a service is no longer enough and you have to evidence it. We designed this as a clinical necessity and it turned into a compliance obligation, so it gets built once and sold twice.
3. **Physician decision policy**, i.e. how the group's best clinicians actually practise, learned from their own adjudicated cases and propagated to all 50 sites. That's the honest version of "digital twin of a doctor": a decision policy rather than a voice or a face. And it has a number, which is plan concordance against blind-adjudicated decisions (SPEC-V1 §8.2). How much of the doctor is in the twin, measured rather than claimed.

Plus one structural advantage: **SIMRS Khanza, the dominant hospital system in the small-hospital segment, is open source.** It's on GitHub, KARS-recognised, with an existing bridging package for BPJS and Dukcapil. We can build the in-form safety net properly instead of negotiating with a vendor.

---

## 11. What could kill it

| # | Risk | Why |
|---|---|---|
| 1 | **Nobody opens it** | Most likely failure, and not technical. Scribe trials saw ~one-third usage. Kenya worked partly because that company employed its doctors and could mandate the workflow. |
| 2 | **Alert fatigue** | 30 features is 30 chances to interrupt. Get it wrong and doctors click through everything, including the one that mattered. |
| 3 | **No reimbursement pull** | Japan's fee schedule pays hospitals to go digital. Indonesia's does not. Adoption rests entirely on an internal mandate, which makes risk #1 worse. Change management is a budget line, not an afterthought. |
| 4 | **Patients can't self-serve intake** | Limited digital literacy is widespread; rural connectivity is poor. A nurse runs the tablet, which works but costs staff time and shrinks the saving. |
| 5 | **Infrastructure** | Roughly 1 in 5 facilities has poor or no internet; about 1 in 12 lacks 24-hour power. Offline-first from day one. |
| 6 | **Payer stress** | BPJS above a 100% claim ratio means harder audits and tariff resistance. Manageable, and partly in our favour, though it caps the upside. |
| 7 | **Data residency** | Indonesian law keeps health data in-country. Shapes every technical decision. Manageable, since sovereign GPU exists. |

---

## 12. First 90 days

1. **Time what doctors actually do.** Three hospitals, a stopwatch, two weeks. Every "60–70%" number is an estimate until this happens.
2. **Pull 1,500 old records** and have Indonesian doctors mark what was missed. That's the scorecard. Without it we can prove nothing.
3. **Ship the paperwork features at one site.** Notes, codes, claim checks, coding sweep. No clinical advice. This is the part that pays.
4. **Run the clinical features silently for a month.** Output goes nowhere but the scorecard. Only when they beat the bar does a doctor see them.
5. **Hire one Indonesian doctor to own the clinical side.** Longest thing to recruit. Nothing clinical ships without them.

---

## 13. Roadmap

| Phase | What | Autonomy |
|---|---|---|
| **0–3 months** | Measure. Time-and-motion at three sites. 1,500 records adjudicated. Prototype on synthetic data. | Shadow |
| **3–9 months** | Documentation, coding, claims live at pilot sites. Revenue lever switched on. | Admin only |
| **9–18 months** | Safety net and suggested diagnosis, one pathway at a time, gated on evidence. | Assist |
| **18–24 months** | Pre-visit intake with drafted plan; doctor countersigns. Regulatory file submitted. | Draft + countersign |
| **Year 3+** | Narrow supervised autonomy on proven pathways. | Supervised |

Never on the roadmap: unsupervised clinical decisions. No jurisdiction permits it, no evidence supports it, no insurer will write it.

---

## 14. The ask

- **USD 3.5–5M** build over 18 months, plus ~USD 0.6M/year infrastructure.
- **2–3 engineers** to prototype; 12–15 to scale.
- **One Indonesian doctor** (STR + SIP) owning clinical governance. Longest lead time on the team, so worth starting now.
- **Three pilot sites** chosen for operational control, not patient volume. This is the Kenya lesson and it matters more than any technical decision.
- **Funding for a quality-improvement study** with blinded adjudication. Not an RCT, since the field hasn't achieved one. But without it there's no regulatory file, no Ministry relationship, and not much we can claim publicly.

---

## 15. How solid are these numbers

Everything above was checked back to a source. Here is what held up and what didn't.

| Claim | Where it comes from | Confidence |
|---|---|---|
| Rp 201T BPJS claims 2025, +14.9% | ANTARA, from BPJS | Solid |
| BPJS claim ratio above 100% in 2025; ~Rp 14.6T shortfall | Kontan, Kompas, from BPJS | Solid |
| Rp 5.92T pending / 3.69M cases (2024) | Bisnis, Kontan. **Now dated**, ~Rp 1.35T by April 2026 | Corrected |
| Private hospitals 20–30% pending | ARSSI, PERSI | Solid |
| 1–5% revenue lost to coding; 11.7% uplift from a documentation fix | International peer-reviewed | Solid |
| "10–20% uplift from coding audits" in Indonesia | Single industry blog, **dropped from the model** | Weak |
| Kenya −16% / −13% | 39,849 visits, blinded physician review | Solid; quality-improvement, not RCT |
| AMIE 90% shortlist accuracy | Google, 100 real patients, one US site | Small study |
| Medical AIs fold ~50% under 5-turn pressure | Preprint, 600 conversations, 20 models | Method solid, not peer reviewed |
| Scribes used in ~⅓ of eligible visits | Randomised trial, 238 physicians | Solid |
| 1 in 5 poor internet, 1 in 12 no 24h power | Peer-reviewed national study | Solid, but *puskesmas*, not hospitals |
| Permenkes 6/2026: capability grading, Art. 74, tariff ceilings | Kemenkes JDIH (enacted 4 Jun 2026); PERSI and law-firm analyses | Solid, implementing rules still pending |
| Capability classification originated in Permenkes 6/2026 | **Wrong, corrected.** It began with PP 28/2024 and Permenkes 11/2025 | Corrected |
| iDRG replacing INA-CBG; severity 3→4 | Kemenkes roadmap | Real but **slipping**, no go-live date |
| Japan 960-hour overtime cap; 5.3% of hospitals lost rural dispatch | MHLW; Dec 2024 survey | Solid (Level A only; higher ceilings are reported inconsistently) |
| ~60% of Japanese hospitals loss-making | Nationwide survey, ~1,800 respondents | Solid |
| Ubie in 100 hospitals; −42.5% on discharge nursing summaries | Company press release, 5 Feb 2026 | **Vendor-reported, directional** |
| No adapted clinical AI benchmark exists in Bahasa Indonesia | Searched; Japan has several, Indonesia none found | Confident, but a negative |
| 43% re-platforming; 61% prioritising claims automation | Black Book survey, Feb 2026, quoted verbatim | **Trade, no methodology disclosed** |
| ~25% EBITDA lift | Our model, inputs stated | **Model, not a forecast** |

**Four numbers can't be inferred from public data and set the size of the prize:** the group's actual BPJS revenue share, its current coding accuracy and pending rate, whether it employs or contracts clinicians, and per-site drug stock. The first three are a two-day finance pull; the fourth is a phone call per site.

*A full list of every correction made across drafts, including the ones where I was wrong, is in [RESEARCH.md § Corrections log](RESEARCH.md#corrections).*

---

## The one line

> We're not building a replacement doctor. We're building the thing that drafts almost everything a doctor would write, so one doctor can safely handle the work of two or three, paid for by money the hospital is already leaving on the table in its billing.
