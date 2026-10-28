# AI Clinician, Indonesia

**Can a 50-hospital Indonesian group build "a digital twin of a doctor that does 60–70% of the job"?**

Short answer: yes, if you allow me one substitution. 60–70% of what a doctor *does* is achievable. 60–70% of what a doctor *decides* probably isn't, because nobody has built that anywhere and I don't think a regulator here would sign it off. Make that swap and the brief turns into an engineering problem. Leave it as written and it stays a research programme.

---

## If you have fifteen minutes

```bash
git clone https://github.com/rishavnaskar/indonesia-doctor-twin.git
cd indonesia-doctor-twin
make          # everything, then the clinician surface opens in a browser
```

Three lines from nothing to a running system, and the third is the only one
that does any work. It creates the virtualenv, installs `requirements.lock`,
starts Postgres if this machine has Docker, runs the architecture rules, the
test suite, the scorecard, the pressure suite and the FHIR bundles against the
official HL7 validator, narrates one encounter per outcome, and then serves the
surface. Open `/clinic` from the header link. Takes roughly two minutes, runs
offline, and needs no key.

Python 3.11 or newer, and nothing else. [CI](.github/workflows/ci.yml) runs
3.11 and 3.13 on every push, and one of its jobs does exactly the three lines
above on a machine that has never seen this repository, then drives the running
server, so the paragraph you just read is checked rather than remembered.

```bash
make live     # the same, with a real model drafting
```

`make live` needs `OPENROUTER_API_KEY` in `.env` and defaults to a free model.
Nothing else is optional-but-required. No Docker, no validator jar and no API
key each turn into a named skip rather than a failure.

**The second run picks up where the first stopped.** Each encounter gets stored
(to Postgres if this machine has Docker, append-only files otherwise) under a
thread id derived from its inputs: patient, site, pack version, which drafter is
behind the router. A re-run replays what's already there instead of doing it
again. `make live` makes 14 model calls the first time and none after that. The
surface alone measured 3m28s, then 1.1s, with identical outcomes. Replayed
encounters say so on every line they print. Edit a guideline file and they all
run again, because a digest of the pack's contents is part of the id.

`python -m tools.store --reset` destroys the lot and starts clean.

`/clinic` keeps what you build there. Patients you generate and run come back
the next time you open it, editable, with their verdicts, signatures and codes,
because they were written to the store rather than to the tab. Clearing that
list deletes nothing. The store refuses `UPDATE` and `DELETE`, so clearing
writes a marker forward and the page starts after it.

Then, in order:

1. **[DECISION.md](docs/DECISION.md) § The reframe**, on why "60–70% of what a doctor does" is buildable and "60–70% of what a doctor decides" probably isn't.
2. **On the demo's scripted page**, click *Hypertensive emergency* and *Remote basic-tier site*. Usually five or six of the nine visits end with no recommendation reaching the doctor. That ratio is sort of the product.
3. **On `/clinic`**, delete a patient's potassium result and run them at SITE-A, then at SITE-C. Same patient, same gap, two different right answers. One asks for the test and the other refers, because only one of those hospitals can run it. **`/sites`** is the record that answer is read from, so you can check the claim rather than take it.
4. **[CODE.md](docs/CODE.md) § Making the drafter better**, which is the measurement that says whether self-consistency earns its cost. It includes the run where it didn't, and the instrument that turned out to be measuring itself.

If you have four, read **[DECISION.md](docs/DECISION.md)** and stop.

---

## What to read

| Doc | What it answers | Time |
|---|---|---|
| **[DECISION.md](docs/DECISION.md)** | Should we do this? What would we build, what would it earn, what could kill it? | ~12 min |
| **[RESEARCH.md](docs/RESEARCH.md)** | Reference. Every claim, source, assumption and correction. Scan it; don't read it end to end. | ~55 min |
| **[BUILD.md](docs/BUILD.md)** | How do we actually build the prototype: stack, order, team, eval bars. | ~15 min |
| **[SPEC-V1.md](docs/SPEC-V1.md)** | The build order for engineers: one pathway, fully specified. Adult hypertension follow-up. | ~12 min |
| **[CODE.md](docs/CODE.md)** | The prototype: what is built, how to run it, what the scorecard does and does not prove. | ~4 min |

**Start with DECISION.md.** RESEARCH and BUILD exist so that every number in it can be traced or attacked. **SPEC-V1 is where the work starts**, since it's the one pathway an engineering team builds first.

---

## The argument in five lines

1. **Reframe the brief.** 60–70% of a doctor's *task-minutes*, not their judgment. 0% of the accountability moves. A licensed Indonesian doctor (STR + SIP) is the sole signer, always.
2. **The evidence supports supervised execution of bounded workflows.** Kenya (39,849 visits) cut diagnostic errors 16% with an AI check a clinician could overrule. The most autonomous clinic on earth still has a human sign every plan. Autonomy beyond that has to be earned pathway by pathway, with evidence.
3. **Ship the boring things first.** Notes, codes and claims carry no clinical risk and pay for the company. The clinical features are the moat, not the payback.
4. **Japan is the proof and the warning.** The same system is being built there, and Japan's own overtime legislation produced our exact task decomposition. But the money argument, the adoption driver, the regulator and the benchmark all fail to transfer.
5. **The safety bar is higher here, not lower.** In Japan the fallback is a tired but qualified doctor. Here it's nobody. Fewer people downstream can catch the machine's mistake.

---

## Building on it

Everything below runs offline and needs no key. [CONTRIBUTING.md](CONTRIBUTING.md)
has the longer version, [CHANGELOG.md](CHANGELOG.md) has what has moved, and
[SECURITY.md](SECURITY.md) has what the design refuses.

```bash
pip install -r requirements-dev.lock   # the tools, on top of the three runtime deps
make check                             # every check CI runs, same order, no browser
make lock                              # regenerate the lockfiles after editing requirements
```

`make check` is lint, types, the architectural rules, the lockfile check, the
test suite with its coverage floor, the scorecard and the pressure suite. The
same set runs on every push and every pull request.

Four of those checks are not style. They encode the constraints that are cheap
now and impossible to retrofit, and `tools/ci_checks.py` explains each at the
top of the file: nothing under `/service` names a country, a payer, a drug or a
guideline; the gate imports nothing; only `/service/graph` touches the
orchestration library; and no hosted tracing endpoint exists anywhere, because
health data must be processed in-country.

A running deployment answers `/health` with which store backend it actually
reached, whether the scripted page built, and what has gone wrong in the
process so far. Logs are one JSON object per line on stderr, with patient
content and credentials dropped by field name before the line is written. There
is no SaaS error tracker and no log drain, deliberately: a stack trace here can
carry the record that produced it.

Every environment variable the system reads is in [.env.example](.env.example).
None is required.

---

## Install

Python 3.11 or newer and nothing else. The three runtime dependencies are
PyYAML, certifi and psycopg; everything else the system does, it does with the
standard library.

```bash
git clone https://github.com/rishavnaskar/indonesia-doctor-twin.git
cd indonesia-doctor-twin
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock        # runtime only
.venv/bin/pip install -r requirements-dev.lock    # plus the test and lint tools
```

`make` does all of that for you, which is why the quick start above is three
lines. The lockfiles are the exact transitive closure, regenerated by `make
lock` and checked against their inputs by `tools/check_lockfiles.py` on every
build, so a resolver that quietly moves a transitive pin fails the build
rather than the demo.

Docker, if you prefer a container:

```bash
docker compose up -d postgres        # the database alone; the service runs on the host
docker build -t clinician .          # or the whole surface as an image
```

## Commands

| Command | What it does |
|---|---|
| `make` | venv, install, Postgres if Docker is present, every check, the walkthrough, then serves the surface |
| `make run` | the surface alone, no checks, no model |
| `make live` | the same with a real model drafting; needs `OPENROUTER_API_KEY` |
| `make check` | lint, types, architectural rules, lockfiles, tests with the coverage floor, scorecard, pressure suite |
| `make lint` | `ruff check` and `ruff format --check` |
| `make types` | `mypy` over `/service` |
| `make test` | `pytest --cov`, which fails under the coverage floor |
| `make audit` | `pip-audit --strict` against `requirements.lock` |
| `make lock` | regenerate both lockfiles in throwaway virtualenvs |
| `make clean` | remove the venv, the store and the caches |
| `python -m tools.store` | what the deployment has kept: summary, signatures, one replayed encounter, or `--reset` |
| `python -m tools.live --list-free` | models that cost nothing right now, queried live |
| `python -m tools.live --show-prompt` | exactly what would be sent, without sending it |
| `python -m tools.validate_fhir` | the outbound bundles against the official HL7 R4 validator |
| `python -m eval.scorecard` | the planted-error scorecard |
| `python -m tools.ci_checks` | the architectural rules on their own |

## Tests

```bash
make test                                   # the suite with its coverage floor
.venv/bin/python -m pytest tests/test_gate_behaviour.py -q    # one file
.venv/bin/python -m pytest -k resume -q                       # one subject
```

Around 420 tests over 35 files, run on 3.11 and 3.13 in CI. Coverage is
measured over `/service` and enforced: `pytest --cov` fails under the floor in
`[tool.coverage.report]`. Tests that need something optional (Docker, the
validator jar, an API key) skip by name rather than fail, so a run on a bare
machine is still a meaningful run.

Four of the checks in `make check` are not style. They encode constraints that
are cheap now and impossible to retrofit, and `tools/ci_checks.py` explains
each at the top of the file: nothing under `/service` names a country, a
payer, a drug or a guideline; the gate imports nothing; only `/service/graph`
touches the orchestration library; and no hosted tracing endpoint exists
anywhere, because health data must be processed in-country.

## Configuration

Every variable the system reads, all of them optional. Placeholders and the
longer explanations are in [.env.example](.env.example); `cp .env.example .env`
and fill in what you need.

| Variable | Default | What it changes |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | the key for `make live`. Without it the drafter is the rule-following reference reasoner, which needs no network |
| `ANTHROPIC_API_KEY` | unset | only for `--provider anthropic`. `ANTHROPIC_AUTH_TOKEN` is the gateway alternative |
| `CLINICIAN_DATABASE_URL` | unset | Postgres. Unreachable or unset, the store falls back to append-only files and logs why |
| `CLINICIAN_STORE` | `.store` | where the file backend writes |
| `CLINICIAN_STORE_BACKEND` | unset | `files` pins the file backend even with a database running. The test suite sets it |
| `CLINICIAN_FRESH` | unset | `1` re-runs work even when a stored result would match |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | where the surface listens. A platform usually sets `PORT` itself |
| `CLINICIAN_HOSTED` | unset | marks a public deployment: the page says so and the reset button is refused |
| `CLINICIAN_ALLOW_RESET` | on locally | permit or refuse the button that destroys the store |
| `CLINICIAN_LOG_LEVEL` | `info` | `debug`, `info`, `warning` or `error`, overridable on a running deployment |
| `CLINICIAN_LOG_FORMAT` | JSON | `plain` makes the lines readable for a person rather than a machine |
| `FHIR_VALIDATOR_JAR` | `.tools/validator_cli.jar` | the official HL7 validator, 190 MB, fetched once. Absent, the run says so and skips |

## HTTP endpoints

| Method | Path | What it answers |
|---|---|---|
| GET | `/` | the scripted walkthrough. Builds once in the background; a reload never re-runs it |
| GET | `/clinic` | the interactive clinician surface. Patients persist across sessions |
| GET | `/sites` | the site capability registry that eligibility routing reads |
| GET | `/health`, `/healthz` | which store backend was reached, whether the build succeeded, and the error tally. `200` ok or degraded, `503` store unreachable. Never triggers a build |
| GET | `/status` | build progress as JSON |
| GET | `/rerun` | force a rebuild of the walkthrough |
| GET | `/api/sites` | `/sites` as JSON |
| GET | `/api/job?id=` | progress of one `/clinic` run |
| GET | `/api/vocabulary` | the pack's codes and labels, for the patient editor |
| GET | `/api/history` | stored `/clinic` visits, and which backend holds them |
| POST | `/api/generate` | generate synthetic patients |
| POST | `/api/run` | run patients through the pipeline; returns a job id |
| POST | `/api/compare` | one patient at two sites, which is the demo's sharpest moment |
| POST | `/api/reset` | destroy the store. Refused on a hosted deployment unless `CLINICIAN_ALLOW_RESET` says otherwise |
| POST | `/api/history/clear` | hide the visit list without deleting anything |

`HEAD` works on every route: health checks, uptime monitors and proxies probe
with it, and a `501` there reads as unhealthy on a service that is fine.

## Layout

| Path | What lives there |
|---|---|
| `service/gate/` | the safety gate. Plain code, no model, no YAML, imports nothing |
| `service/rules/` | predicates, targets and pathway selection |
| `service/packs/` | the loader for the rule packs, and their schema |
| `service/graph/` | the orchestration library, confined here by a CI check |
| `service/reason/` | prompts and the strict parser the drafter's output faces |
| `service/router/` | which drafter answers: reference reasoner, hosted model, or Anthropic |
| `service/contracts/` | the typed proposal every drafter must produce |
| `service/emit/` | FHIR bundles and the outbound queue |
| `service/store.py`, `service/db.py` | the two backends behind one object |
| `service/logging.py` | structured logs, field-name redaction, the error tally |
| `packs/` | the rule packs. A second pathway went in as two files here and no engine code |
| `datagen/` | synthetic patients and the planted errors the scorecard grades |
| `eval/` | the scorecard and the pressure suite |
| `tools/demo/` | the HTTP surface: routes, pages, the background build |
| `tests/` | 35 files. Named for the behaviour they hold, not the module |
| `docs/` | the argument, the research behind it, and the build order |

---

## Status

**Complete.** Research and business case verified and independently re-reviewed by a second model. V1 pathway specified. Prototype built, measured and green, with every pathway step in SPEC-V1 §5 implemented and tested. What remains needs a clinical lead, a hospital and 300 adjudicated visits, none of which is an engineering task; the list is at the end of [CODE.md](docs/CODE.md).

The safety gate, the Indonesian rule packs, eligibility routing, the signature line and the scorecard all run today, on synthetic patients, with no model involved. That ordering is deliberate: the gate is the part that has to be right, it needs nothing else running, and building it first means a model arrives into a system that already refuses bad output.

A real model now sits behind the router and changed nothing downstream, which was the architectural claim, tested rather than assumed. **A second pathway (type 2 diabetes follow-up) went in as two pack files with no engine code**, which was the other one. It runs through the tests, the FHIR validation and both demo surfaces, though not through the scorecard, whose planted errors are all hypertension mutations, so the 7/7 below is a statement about one pathway. Building it turned up several places where that claim hadn't been true: the target contract was shaped around blood pressure, refusal routing had learned one pack's rule-numbering convention, the claim coder produced no primary diagnosis for a second disease, and the FHIR emitter shipped a diabetes encounter without its HbA1c. All fixed and tested now. Finding them was probably worth more than the pathway itself.

The outbound bundles validate with **0 errors against the official HL7 FHIR R4 validator** (downloaded once by `python -m tools.validate_fhir --help`; the run says so if it is absent). It found nine errors that a hand-written conformance test had missed, one of which that test had itself introduced.

This has been through six drafts and four adversarial review passes, the last a full independent review by a second model. Twenty-three claims turned out to be wrong, overstated or internally inconsistent, and got corrected. The full list, including the ones that were mine, is in [RESEARCH.md § Corrections log](docs/RESEARCH.md#corrections). If you're reviewing this, I'd start there, since it's the fastest way to find the parts of the argument that have already moved.

Four numbers cannot be established from public sources and set the size of the prize: the group's actual BPJS revenue share, its current coding accuracy and pending-claim rate, whether it employs or contracts its clinicians, and per-site drug stock. Each is a replaceable input, not a blocker.

---

## Non-negotiables carried into the build

These are constraints, not preferences. They come from Indonesian law and from the failure literature, and they should survive any redesign.

- **A licensed doctor signs everything.** Nothing with clinical effect leaves the room unsigned. Enforced in software.
- **Health data stays in Indonesia.** GR 28/2024 requires storage *and* processing in-country; UU PDP 27/2022 requires an explicit lawful basis for health data plus a DPIA for high-risk processing.
- **No hosted agent control plane.** Self-hosted orchestration only, and never a SaaS tracing backend, which would quietly ship PHI offshore. There's a CI check for it in BUILD.md.
- **The safety gate is plain code, never a model.** It must be readable by a doctor, diffable in git, and testable with nothing else running.
- **Synthetic patient data only, until there is a lawful basis for real records.**
- **No open-ended patient symptom chat.** Bounded interview only. The sycophancy evidence in RESEARCH.md §3 is fairly unambiguous on this.
- **Never personify the system as a named real doctor.** A product name and an obviously synthetic voice. Modelling a clinician's decision policy is legitimate; wearing their face is not.
- **Text the system did not author is data, never instruction.** Patient utterances, record free text, scanned documents: all of it delimited before any model sees it, and everything the model produces faces the gate regardless. Prompt injection is a named failure mode (SPEC-V1 F11), not an afterthought.
- **Never let an architecture assumption masquerade as a legal conclusion.** Residency, device classification, lawful basis for data. Each gets confirmed by Indonesian counsel, and the architecture encodes the conservative reading until then.

---

## Note on earlier versions

Two of these documents were previously circulated as web pages. Their content is the same as `DECISION.md` and `RESEARCH.md` respectively; the markdown here is now the canonical version. `BUSINESS.md` and `JAPAN.md` have been merged into `DECISION.md` and `BUILD.md` and no longer exist as separate files.
