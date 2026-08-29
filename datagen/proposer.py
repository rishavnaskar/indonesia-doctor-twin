"""Thin alias to the reference reasoner.

The reasoner itself moved into /service/reason once its escalation ladder moved
into the pack — before that it hard-coded molecule names, which /service is not
allowed to do. Kept here so the generators read naturally.
"""

from service.packs.loader import load_pack as _load_pack
from service.reason.reference import _provenance, propose as _propose

_DEFAULT_SITE = None


def propose(state, rules, site=None):
    return _propose(state, rules, site)


def reference_provenance(rules):
    return _provenance(rules)


# Back-compat for callers that imported the constant directly.
REFERENCE_PROVENANCE = _provenance(_load_pack("id"))
