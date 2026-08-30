# Demo script

A running order for a recorded walkthrough. Roughly 12 minutes. Every number
below comes from a real run; if one of them has moved by the time you record,
say the number you see rather than the number written here.

Two rules for the recording. **Show a refusal before you show a success** —
otherwise the audience calibrates on the happy path and the refusals look like
failures when they arrive. And **do not skip the mistakes**: the corrections are
the most persuasive material here, because they are the part nobody can fake.

---

## 0 · Before you start (30s, off-camera)

```bash
make all          # everything green, no API key needed
make surface      # leave it running at http://127.0.0.1:8000
```

Have two tabs open: the scripted page `/` and the interactive one `/clinic`.

---

## 1 · The reframe (90s, no screen)

> "The brief asks for a digital twin of a doctor doing 60–70% of the job. That is
> achievable — for 60–70% of what a doctor **does**. It is not achievable for
> 60–70% of what a doctor **decides**, because nobody has built that and no
> regulator would permit it. So: 60–70% of task-minutes, 0% of the accountability
> moves. A licensed Indonesian doctor signs everything, and that is enforced in
> software, not in policy."

Then say what the twin actually is: a state machine over a longitudinal patient
model, not a conversation. The brief explicitly said not chat-based, and this
is why — the pressure suite finding, one line: a sycophantic control folds to a
confidently wrong patient on turn 3 of 6 cases out of 6. The shipped intake
cannot, because it has no clinical voice to be argued out of.

---

## 2 · The refusals (3 min, scripted page)

Open `/`. Point at the header: **5 of 9 visits ended with no recommendation
reaching the doctor.**

> "That ratio is the product. A demo where the assistant always has an answer is
> a demo of a system nobody should deploy."

Click through three, in this order:

**Hypertensive emergency** → red, must be acknowledged, Bahasa first with the
English beneath. The one case where the system interrupts a clinician who has
not asked.

**The same case, with the dose out by ten** → switch to *What the doctor sees*.
Nothing. The decimal-point error is the most plausible failure there is; the
draft never reaches the clinician, and the reason is in the audit view rather
than on their screen.

**Remote basic-tier site** → *What the system did*. Nine checks with ticks and
crosses, each finding with its rule id and citation, the site's actual lab list,
the three provenance pins.

> "A plan is only a plan if this hospital can carry it out. SITE-C cannot run a
> potassium assay, so the correct output is a referral, not a recommendation."

---

## 3 · Change something and watch it move (3 min, `/clinic`)

Generate 3 patients. Then, live:

1. Set one patient's systolic to **212**, tick **chest pain**, run → that card
   flips to `escalate`.
2. Clear a patient's **potassium** and **eGFR**, run at **SITE-A** → `request_info`,
   "get the potassium".
3. Change the hospital dropdown to **SITE-C**, run again, touching nothing else →
   `abstain`, converted to a referral.

> "Same patient, same missing test, two different right answers — because only
> one of those hospitals can run it."

While it runs, point out that the form is locked and each card shows the phase
it is actually in. `PROPOSE` is where a live run spends its time.

Open **"How do I know it actually checked?"** on one card.

---

## 4 · The model is a component (2 min)

Toggle **Draft with a real AI model**, re-run.

> "Same nine checks, same gate, same signature line. The only thing that changed
> is who wrote the draft."

Then the finding worth the whole section — the diabetic patient with no
extracted target:

> "The rule-following version says *refer*. The AI model says *titrate up* — it
> tried to treat a patient whose blood-pressure target we have never extracted.
> The model made a worse clinical call and the outcome was identical, because
> the gate does not care which drafter produced the proposal."

---

## 5 · A second disease, as data (2 min)

Click the three diabetes scenarios.

> "Type 2 diabetes. Two pack files and no engine code — same nine checks, same
> gate, same signature. That was the claim. Building it proved the claim false in
> three places: the target contract had a blood pressure baked into it, refusal
> routing had learned one pack's rule-numbering convention, and the claim coder
> produced no primary diagnosis for the second disease. All three are fixed."

> "That is why you build the second one. A claim nobody has tested is a claim."

---

## 6 · What is not proven (90s, no screen)

Do not skip this. It is the most credible thing you will say.

- Sets A and B are generated from the same guideline the gate checks against.
  They prove the plumbing and prove nothing clinical.
- **Set C — 300 real visits, physician-adjudicated — does not exist**, and every
  number here is caveated on it.
- The rule packs are `awaiting_clinical_signoff`. Three blood-pressure targets
  are missing, and the system correctly abstains on those subgroups today.
- Self-consistency: two runs, 58 drafts, all 4 errors were in the unstable
  group, p = 0.0043. It is left **off by default** anyway, because the labels
  came from our own rule engine — so it predicts divergence from us, not
  clinical error, and that is a different claim.

Close on the first measurement that said the technique was worthless, and why
it was wrong: it had been measured through the mechanism it was evaluating, so
the abstention floor had already deleted every unstable draft before the
comparison ran.

> "The technique is unremarkable. Not believing the first measurement is the
> part I would want reviewed."
