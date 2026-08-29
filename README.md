# AI Clinician — Indonesia

**Can a 50-hospital Indonesian group build "a digital twin of a doctor that does 60–70% of the job"?**

Short answer: **yes.** The brief asks for 60–70% of what a doctor *does* — and that is achievable. What it cannot mean is 60–70% of what a doctor *decides*, because nobody in the world has built that and no regulator would permit it. Same target, and the distinction is what makes it buildable rather than a research programme.

---

## What to read

| Doc | What it answers | Time |
|---|---|---|
| **[DECISION.md](DECISION.md)** | Should we do this? What would we build, what would it earn, what could kill it? | ~12 min |
| **[RESEARCH.md](RESEARCH.md)** | Reference. Every claim, source, assumption and correction. Scan it; don't read it end to end. | ~55 min |
| **[BUILD.md](BUILD.md)** | How do we actually build the prototype — stack, order, team, eval bars. | ~15 min |
| **[SPEC-V1.md](SPEC-V1.md)** | The build order for engineers: one pathway, fully specified. Adult hypertension follow-up. | ~12 min |
| **[CODE.md](CODE.md)** | The prototype: what is built, how to run it, what the scorecard does and does not prove. | ~4 min |

**Start with DECISION.md.** RESEARCH and BUILD exist so that every number in it can be traced or attacked. **SPEC-V1 is where the work actually starts** — it is the one pathway an engineering team builds first.

---

## The argument in five lines

1. **Reframe the brief.** 60–70% of a doctor's *task-minutes*, not their judgment. 0% of the accountability moves. A licensed Indonesian doctor (STR + SIP) is the sole signer, always.
2. **The evidence supports supervised execution of bounded workflows.** Kenya (39,849 visits) cut diagnostic errors 16% with an AI check a clinician could overrule. The most autonomous clinic on earth still has a human sign every plan. Autonomy beyond that has to be earned pathway by pathway, with evidence.
3. **Ship the boring things first.** Notes, codes and claims carry no clinical risk and pay for the company. The clinical features are the moat, not the payback.
4. **Japan is the proof and the warning.** The same system is being built there, and Japan's own overtime legislation produced our exact task decomposition. But the money argument, the adoption driver, the regulator and the benchmark all fail to transfer.
5. **The safety bar is higher here, not lower.** In Japan the fallback is a tired but qualified doctor. Here it's nobody. Fewer people downstream can catch the machine's mistake.

---

## Status

**Research and business case: complete and verified. V1 pathway: specified. Independently re-reviewed by a second model. Prototype: the deterministic core is built and green — see [CODE.md](CODE.md).**

The safety gate, the Indonesian rule packs, eligibility routing, the signature line and the scorecard all run today, on synthetic patients, with no model involved. That ordering is deliberate: the gate is the part that has to be right, it needs nothing else running, and building it first means a model arrives into a system that already refuses bad output.

This has been through six drafts and four adversarial review passes, the last a full independent review by a second model. Twenty-three claims were found wrong, overstated or internally inconsistent and corrected — the full list, including the ones that were mine, is in [RESEARCH.md § Corrections log](RESEARCH.md#corrections). If you are reviewing this, start there; it is the fastest way to find the parts of the argument that have already moved.

Four numbers cannot be established from public sources and set the size of the prize: the group's actual BPJS revenue share, its current coding accuracy and pending-claim rate, whether it employs or contracts its clinicians, and per-site drug stock. Each is a replaceable input, not a blocker.

---

## Non-negotiables carried into the build

These are constraints, not preferences. They come from Indonesian law and from the failure literature, and they should survive any redesign.

- **A licensed doctor signs everything.** Nothing with clinical effect leaves the room unsigned. Enforced in software.
- **Health data stays in Indonesia.** GR 28/2024 requires storage *and* processing in-country; UU PDP 27/2022 requires an explicit lawful basis for health data plus a DPIA for high-risk processing.
- **No hosted agent control plane.** Self-hosted orchestration only — never a SaaS tracing backend, which would quietly ship PHI offshore. There's a CI check for it in BUILD.md.
- **The safety gate is plain code, never a model.** It must be readable by a doctor, diffable in git, and testable with nothing else running.
- **Synthetic patient data only, until there is a lawful basis for real records.**
- **No open-ended patient symptom chat.** Bounded interview only — the sycophancy evidence in RESEARCH.md §3 is unambiguous.
- **Never personify the system as a named real doctor.** A product name and an obviously synthetic voice. Modelling a clinician's decision policy is legitimate; wearing their face is not.
- **Text the system did not author is data, never instruction.** Patient utterances, record free text, scanned documents — all delimited before any model sees them, and everything the model produces faces the gate regardless. Prompt injection is a named failure mode (SPEC-V1 F11), not an afterthought.
- **Never let an architecture assumption masquerade as a legal conclusion.** Residency, device classification, lawful basis for data — each gets confirmed by Indonesian counsel; the architecture encodes the conservative reading until then.

---

## Note on earlier versions

Two of these documents were previously circulated as web pages. Their content is the same as `DECISION.md` and `RESEARCH.md` respectively; the markdown here is now the canonical version. `BUSINESS.md` and `JAPAN.md` have been merged into `DECISION.md` and `BUILD.md` and no longer exist as separate files.
