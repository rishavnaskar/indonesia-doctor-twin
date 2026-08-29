"""The gate's import graph is a safety property, so it gets a test.

If someone adds `import langgraph` to a check because it was convenient, this
fails before review. The rule is not aesthetic: the gate has to be readable by a
doctor, runnable in isolation, and free of anything that could put a model
inside it.
"""

import subprocess
import sys


def test_gate_imports_nothing_it_should_not():
    code = (
        "import service.gate, sys;"
        "banned=[m for m in ('yaml','langgraph','langchain','langsmith') if m in sys.modules];"
        "print(','.join(banned))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"gate pulled in: {result.stdout.strip()}"


def test_ci_checks_pass():
    result = subprocess.run(
        [sys.executable, "tools/ci_checks.py"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout
