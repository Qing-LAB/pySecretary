from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


_UNSET = object()


@dataclass(frozen=True)
class LLMRequest:
    """A unit of work that needs an LLM update.

    Requests are grouped by ``context_key``. Requests in the same context are combined
    into one LLM call; different context keys are independent (e.g. different clients or
    streams). ``sequence`` orders requests within a context, and ``depends_on`` records the
    sequence this one continues, so a coalesced batch stays in dependency order.
    """

    context_key: str
    sequence: int
    payload: Any
    depends_on: int | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class _Context:
    pending: list[LLMRequest] = field(default_factory=list)
    in_flight: bool = False
    state: Any = None


class LLMRequestQueue:
    """Coalescing request queue for LLM update calls.

    Pending requests for the same ``context_key`` are combined into a single batch when the
    context is dispatched, so the model receives one update request (with the combined
    content and the context's carried state) instead of many small ones. Unrelated context
    keys are independent waiting lists and never combine — which naturally separates
    different clients/streams. A context processes at most one batch at a time; requests
    submitted while a context is in flight accumulate and are coalesced on the next dispatch.

    The queue is transport-agnostic and does no LLM I/O itself: a worker claims a batch with
    :meth:`begin`, runs the actual LLM call, then calls :meth:`complete` (optionally storing
    the new carried state). :meth:`process_available` wraps that loop for simple callers.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, _Context] = {}
        self._lock = threading.RLock()

    def submit(self, request: LLMRequest) -> None:
        with self._lock:
            self._contexts.setdefault(request.context_key, _Context()).pending.append(request)

    def has_pending(self, context_key: str | None = None) -> bool:
        with self._lock:
            if context_key is not None:
                ctx = self._contexts.get(context_key)
                return bool(ctx and ctx.pending)
            return any(ctx.pending for ctx in self._contexts.values())

    def pending_count(self, context_key: str | None = None) -> int:
        with self._lock:
            if context_key is not None:
                ctx = self._contexts.get(context_key)
                return len(ctx.pending) if ctx else 0
            return sum(len(ctx.pending) for ctx in self._contexts.values())

    def is_in_flight(self, context_key: str) -> bool:
        with self._lock:
            ctx = self._contexts.get(context_key)
            return bool(ctx and ctx.in_flight)

    def dispatchable_contexts(self) -> list[str]:
        """Context keys that have pending work and are not already in flight."""
        with self._lock:
            return [key for key, ctx in self._contexts.items() if ctx.pending and not ctx.in_flight]

    def peek(self, context_key: str) -> LLMRequest | None:
        with self._lock:
            ctx = self._contexts.get(context_key)
            if not ctx or not ctx.pending:
                return None
            return min(ctx.pending, key=lambda request: request.sequence)

    def begin(self, context_key: str) -> list[LLMRequest] | None:
        """Coalesce and claim all pending requests for a context, in dependency order.

        Returns the combined batch (sorted by ``sequence``) and marks the context in flight,
        or ``None`` if the context has no pending work or is already in flight.
        """
        with self._lock:
            ctx = self._contexts.get(context_key)
            if not ctx or ctx.in_flight or not ctx.pending:
                return None
            batch = sorted(ctx.pending, key=lambda request: request.sequence)
            ctx.pending = []
            ctx.in_flight = True
            return batch

    def complete(self, context_key: str, state: Any = _UNSET) -> None:
        """Release the in-flight slot for a context, optionally storing carried state."""
        with self._lock:
            ctx = self._contexts.get(context_key)
            if ctx is None:
                return
            ctx.in_flight = False
            if state is not _UNSET:
                ctx.state = state

    def get_state(self, context_key: str) -> Any:
        with self._lock:
            ctx = self._contexts.get(context_key)
            return ctx.state if ctx else None

    def set_state(self, context_key: str, state: Any) -> None:
        with self._lock:
            self._contexts.setdefault(context_key, _Context()).state = state

    def clear(self, context_key: str | None = None) -> None:
        with self._lock:
            if context_key is None:
                self._contexts.clear()
            else:
                self._contexts.pop(context_key, None)

    def process_available(
        self,
        handler: Callable[[str, list[LLMRequest], Any], Any],
        can_dispatch: Callable[[str], bool] | None = None,
    ) -> int:
        """Dispatch one coalesced batch per ready context through ``handler``.

        ``handler(context_key, batch, state)`` runs the actual LLM call and returns the new
        carried state. ``can_dispatch(context_key)`` can gate dispatch (e.g. to give STT
        priority on a shared server). Returns the number of contexts dispatched.
        """
        dispatched = 0
        for context_key in self.dispatchable_contexts():
            if can_dispatch is not None and not can_dispatch(context_key):
                continue
            batch = self.begin(context_key)
            if batch is None:
                continue
            new_state: Any = _UNSET
            try:
                new_state = handler(context_key, batch, self.get_state(context_key))
            finally:
                self.complete(context_key, new_state)
            dispatched += 1
        return dispatched
