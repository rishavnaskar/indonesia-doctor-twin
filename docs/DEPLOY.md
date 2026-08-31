# Putting the surface on a public URL

For a reviewer who should be able to click a link and use the thing, rather
than clone a repository and run `make`. Everything below is on free plans and
needs no card.

The deployed thing is **the surface only**. `make` runs the gates and then
serves, which is right for a developer and wrong for a platform: a container
restarting should answer a health check in seconds, not re-run a test suite
first. CI is where the gates belong.

## What gets deployed

| | |
|---|---|
| Web service | The clinician surface — `/` scripted, `/clinic` interactive |
| Postgres | Checkpoints, signatures, outbound queue. Free plan |
| Drafting | A real model, **replayed from the store** — see below |

## The part worth understanding: a live page that makes no live calls

A page load must not cost a model call. Nine calls per view is slow, spends
somebody's key on every visitor, and is one rate limit away from a page of
errors in front of the person you wanted to impress.

It does not have to. Encounters are stored under a thread id derived from their
inputs, so seeding the production store with one live run before launch means
every page load afterwards replays it: **real provenance, real refusals, zero
calls, instant**. The resumption machinery doing exactly what it was built for.

`/clinic` still drafts live when the visitor ticks *Draft with a real AI model*,
which is the interactive part worth having. That does spend the key, on free
models.

## Runbook

**1. Make the repository public**, then push. `render.yaml` and `Dockerfile`
are already in it.

**2. Create the services.** Render → **New → Blueprint** → pick this repository.
It reads `render.yaml` and creates the web service and the Postgres together.

**3. Add the key.** In the web service → **Environment**, set
`OPENROUTER_API_KEY`. It is marked `sync: false` in the blueprint precisely so
it never lives in the repository. Without it the entrypoint falls back to the
reference reasoner rather than failing — the page still works, it just says a
model was not involved.

**4. Seed the store, so the first visitor waits for nothing.** Copy the
database's **External Connection String** from the Render dashboard, then run
one live pass against it from your machine:

```bash
CLINICIAN_DATABASE_URL='<external connection string>' \
  ./.venv/bin/python -m tools.demo --live --export /tmp/seed.html
```

Nine model calls, a few minutes, once. Every page load after that is a replay.
No extra tooling — it is the same command that exports the offline page.

**5. Open the URL.** The header should say `9 of 9 replayed from the store, not
re-run` and name the model that actually served them.

## What to expect, and what to say about it

**It sleeps.** A free web service stops after 15 minutes idle and takes roughly
a minute to wake. The first click after a quiet period is slow; every one after
is not. Worth a sentence when you share the link.

**The database is deleted after 30 days** on the free plan. The system survives
it — with no database reachable the store falls back to append-only files and
says which it chose on the page — but the encounter history resets and the
scripted page will re-run live on first load. Re-seed, or move
`CLINICIAN_DATABASE_URL` to any other Postgres; nothing else changes.

**Data residency, which a reviewer should raise.** This document argues that
Indonesian law requires health data to be processed in-country, and this
deployment is not in Indonesia. That is not an oversight and the demo says so on
its own front page: every patient in it is generated, and the residency guard
enforces that rather than trusting it — a record not marked synthetic is refused
before any request to a hosted model is built. Pointing this deployment at a
real patient fails closed instead of quietly exporting one. The hosted demo is a
demonstration of the guard, not an exception to it. Production runs in-country
on sovereign infrastructure; that is a hosting decision, and the architecture
does not change.

**A public /clinic accepts pasted records**, so the page carries a banner
telling visitors not to paste a real one. The guard is the control; the banner
is so the situation does not arise.

## Running the container locally

```bash
docker build -t clinician-surface .
docker run -p 8099:8000 \
  -e CLINICIAN_DATABASE_URL='postgresql://clinician:clinician@host.docker.internal:5544/clinician' \
  clinician-surface
```

Add `-e CLINICIAN_LIVE=1 -e OPENROUTER_API_KEY=...` to draft with a model.
Without a database it runs on files, which are ephemeral in a container — fine
for a smoke test, wrong for anything you want to still be there tomorrow.

## Other hosts

Nothing here is Render-specific except `render.yaml`. The image reads `PORT`
and `HOST` from the environment and `CLINICIAN_DATABASE_URL` for state, so any
platform that runs a container works — Fly, Koyeb, a Hugging Face Space, Cloud
Run. Only the blueprint would need rewriting.
