# First EMR adapter — environment scaffold

**Status: scaffolded, not yet verified against the real application.** Nothing
here has been run against the actual hospital system. Treat every schema
assumption below as unconfirmed until Phase 0 is signed off.

## Why this system first

It is the dominant hospital information system in the small-hospital segment,
it is open source and published on GitHub, it is recognised by the accreditation
commission, and its repository already contains a bridging package doing
integrations of exactly the shape we need. That last point matters most: the
pattern we need is not novel to this codebase, it is how the codebase already
works.

The consequence is that assumption A1 — can we render a traffic light *inside*
the consultation form — is resolved for the majority of the estate. We have the
source, so the safety net can live in the form rather than on a second screen.

## What Phase 0 has to prove

1. The application runs with a seeded database.
2. Synthetic patients written into the native schema are visible in the client.
3. A no-op panel can be added to the outpatient consultation form, and the
   round trip can be timed.

Item 3 is the one that matters. One engineer, two days, per the assumption
register.

## Deliberately not done yet

- No schema is committed here. Copying a guessed schema into the repo would
  create something that looks authoritative and is not.
- We read from the native database and write our own state. We do not write to
  the legacy schema.

## Next step

Pull the upstream repository, stand up the database from its own migrations,
and replace `adapter.py` with a real mapping. Until then the adapter raises
rather than returning a plausible-looking empty state — a fake read is worse
than a failed one.
