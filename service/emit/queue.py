"""The outbound queue.

Offline-first is a requirement here, not a nicety: roughly one site in five has
unreliable connectivity and about one in twelve lacks 24-hour power. A design
that assumes a live round trip fails at one hospital in five, and the ones it
fails at are exactly the remote sites this whole programme exists to serve.

So nothing is sent inline. Work is enqueued durably, and a separate drain sends
it when there is a network. Two properties matter:

  * **Nothing is lost.** The queue is append-only on disk and survives a restart
    or a power cut mid-consultation.
  * **Nothing is duplicated.** Every item carries an idempotency key. Replaying
    the same encounter after a dropped connection is a no-op rather than a
    second encounter in the national record.

The transport is deliberately abstract. This module never opens a socket, which
is what lets it be tested exhaustively with no network and no sandbox.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator


class ItemStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class QueueItem:
    idempotency_key: str
    kind: str
    payload: dict[str, Any]
    enqueued_at: str
    status: ItemStatus = ItemStatus.PENDING
    attempts: int = 0
    last_error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "idempotency_key": self.idempotency_key,
                "kind": self.kind,
                "payload": self.payload,
                "enqueued_at": self.enqueued_at,
                "status": self.status.value,
                "attempts": self.attempts,
                "last_error": self.last_error,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(line: str) -> "QueueItem":
        raw = json.loads(line)
        return QueueItem(
            idempotency_key=raw["idempotency_key"],
            kind=raw["kind"],
            payload=raw["payload"],
            enqueued_at=raw["enqueued_at"],
            status=ItemStatus(raw["status"]),
            attempts=raw["attempts"],
            last_error=raw.get("last_error"),
        )


@dataclass
class OutboundQueue:
    """Append-only, file-backed, idempotent."""

    path: Path | None = None
    items: dict[str, QueueItem] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)
    # Lines the log could not parse. Kept rather than discarded: a queue that
    # quietly drops part of its own history is worse than one that says so.
    damaged: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path is not None and Path(self.path).exists():
            self._load()

    # ------------------------------------------------------------- writing

    def enqueue(self, kind: str, payload: dict[str, Any], idempotency_key: str,
                now: datetime | None = None) -> QueueItem:
        existing = self.items.get(idempotency_key)
        if existing is not None:
            # Already known. Re-enqueueing after a dropped connection is a
            # no-op, which is the entire point of the key.
            return existing

        item = QueueItem(
            idempotency_key=idempotency_key,
            kind=kind,
            payload=payload,
            enqueued_at=(now or datetime.now()).isoformat(timespec="seconds"),
        )
        self.items[idempotency_key] = item
        self._order.append(idempotency_key)
        self._append(item)
        return item

    def mark(self, idempotency_key: str, status: ItemStatus, error: str | None = None) -> None:
        item = self.items[idempotency_key]
        item.status = status
        item.last_error = error
        self._append(item)

    # ------------------------------------------------------------- reading

    def pending(self) -> list[QueueItem]:
        return [self.items[k] for k in self._order if self.items[k].status is ItemStatus.PENDING]

    def __iter__(self) -> Iterator[QueueItem]:
        return (self.items[k] for k in self._order)

    def __len__(self) -> int:
        return len(self._order)

    # ------------------------------------------------------------ draining

    def drain(self, send: Callable[[QueueItem], None], *, max_items: int | None = None) -> dict:
        """Attempt to send pending work.

        A failure leaves the item pending rather than dropping it, and the drain
        keeps going — one unreachable endpoint must not block an unrelated
        encounter behind it.
        """
        sent = failed = 0
        for item in self.pending()[: max_items or None]:
            item.attempts += 1
            try:
                send(item)
            except Exception as exc:  # noqa: BLE001 - transports fail; that is the point
                self.mark(item.idempotency_key, ItemStatus.PENDING, f"{type(exc).__name__}: {exc}")
                failed += 1
                continue
            self.mark(item.idempotency_key, ItemStatus.SENT)
            sent += 1
        return {"sent": sent, "failed": failed, "still_pending": len(self.pending())}

    # ------------------------------------------------------------ durability

    def _append(self, item: QueueItem) -> None:
        if self.path is None:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(item.to_json() + "\n")

    def _load(self) -> None:
        """Replay the log. Later entries for a key win.

        A line that will not parse is skipped and recorded, not raised. The log
        is append-only and written a line at a time, so a power cut mid-write
        leaves a truncated final line — and about one site in twelve lacks
        24-hour power, which makes that the expected case rather than the exotic
        one. Refusing to open the file would lose every encounter behind the
        damaged line, which is the precise outcome this queue exists to prevent.

        Skipped lines are counted in `damaged` so the loss is visible. Silently
        dropping part of a clinical audit log would be worse than crashing.
        """
        for line in Path(self.path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = QueueItem.from_json(line)
            except (json.JSONDecodeError, KeyError, ValueError):
                self.damaged.append(line[:200])
                continue
            if item.idempotency_key not in self.items:
                self._order.append(item.idempotency_key)
            self.items[item.idempotency_key] = item
