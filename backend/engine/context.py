from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Callable


@dataclass
class ExecutionContext:
    """Runtime context passed across workflow execution."""

    ticket_id: int | None = None
    node_outputs: dict[str, Any] = field(default_factory=dict)
    store: dict[str, Any] = field(default_factory=dict)
    event_queue: Queue | None = None
    emit_fn: Callable[..., Any] | None = None

