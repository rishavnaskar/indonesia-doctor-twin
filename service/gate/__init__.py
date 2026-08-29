"""The deterministic gate.

The thing that lets any of the rest near a patient. Everything above it is
probabilistic and replaceable; everything at this line is plain code,
auditable, and version-controlled.

Import rules, enforced by tools/ci_checks.py and by a test that inspects
sys.modules after import:

  * never imports the orchestration library
  * never imports from /service/reason
  * never pulls YAML into its import graph
  * no model, ever
"""

from service.gate.engine import run_gate
from service.gate.types import Finding, GateContext, GateDecision, Severity

__all__ = ["run_gate", "Finding", "GateContext", "GateDecision", "Severity"]
