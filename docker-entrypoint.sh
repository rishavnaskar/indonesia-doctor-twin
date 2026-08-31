#!/bin/sh
# Decide whether the hosted surface drafts with a real model.
#
# Not a CMD flag, because the answer depends on what the deployment has rather
# than on what the image was built with. With CLINICIAN_LIVE=1 and a key, the
# page reports real provenance — replayed from the store, so a page load costs
# nothing. Without either, it falls back to the reference reasoner, which is
# the documented default and still shows every gate decision.
#
# The guard is the `-n` test on the key. `--live` with no key would try nine
# model calls at startup and fail all nine, and a container that serves a page
# of errors is worse than one that serves the deterministic version.
set -e

LIVE=""
if [ "${CLINICIAN_LIVE:-}" = "1" ] && [ -n "${OPENROUTER_API_KEY:-}" ]; then
  LIVE="--live"
  echo "  Drafting: real model (replayed from the store where one is on record)"
else
  echo "  Drafting: reference reasoner — no key, or CLINICIAN_LIVE is not 1"
fi

exec python -m tools.demo --no-open $LIVE "$@"
