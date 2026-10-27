"""What /clinic ran in earlier sessions, read back out of the store.

The interactive page was the one part of the system that kept nothing: its
results lived in a dict in the server process and its patients lived in the
browser tab, so closing either one lost the work. They were being written to
the store the whole time and nothing was reading them back.
"""

from __future__ import annotations

from datetime import datetime

from tools.demo.store_access import runtime

CLEAR_MARKER = "CLINIC-HISTORY-CLEARED"


def clinic_history(limit: int = 24) -> list[dict]:
    """Visits run at /clinic in earlier sessions, newest first.

    The interactive page was the one part of the system that kept nothing: its
    results lived in a dict in the server process and its patients lived in the
    browser tab, so closing either one lost the work. They were being written to
    the store the whole time — nothing was reading them back.
    """
    since = _cleared_at()
    latest: dict[str, dict] = {}
    for history in runtime().checkpoints.values():
        for entry in reversed(history):
            if entry.step != "rendered" or not isinstance(entry.state, dict):
                continue
            view = entry.state
            if view.get("origin") != "clinic":
                break
            ran_at = view.get("ran_at") or ""
            if since and ran_at <= since:
                break
            # One card per patient: re-running the same record is the same
            # patient seen again, not a second patient.
            keep = latest.get(view.get("key"))
            if keep is None or ran_at > (keep.get("ran_at") or ""):
                latest[view.get("key")] = view
            break
    ordered = sorted(latest.values(), key=lambda v: v.get("ran_at") or "", reverse=True)
    return ordered[:limit]


def clear_clinic_history() -> str:
    """Hide what is on the page without deleting any of it.

    The store refuses UPDATE and DELETE — that is the point of it — so clearing
    is a marker written forward rather than history rewritten backwards. The
    visits stay on the record and remain replayable by `python -m tools.store`;
    the page simply starts after the marker. An audit log with a clear button
    that worked would not be an audit log.
    """
    at = datetime.now().isoformat()
    runtime().checkpoint(CLEAR_MARKER, "rendered", {"origin": "cleared", "ran_at": at})
    return at


def _cleared_at() -> str:
    history = runtime().checkpoints.get(CLEAR_MARKER) or []
    stamps = [e.state.get("ran_at", "") for e in history
              if isinstance(e.state, dict) and e.state.get("origin") == "cleared"]
    return max(stamps) if stamps else ""


