# Coalescing LLM Request Queue (`pysecretary.llm_queue`)

This document is the source of truth for `pysecretary.llm_queue`. Update it whenever the
request contract, coalescing rules, dispatch lifecycle, or multi-context behavior change.

## Purpose

LLM update calls (transcript cleanup today; analysis/summary later) should not be issued one
tiny request at a time. `pysecretary.llm_queue` is a **coalescing request queue**: pending
requests that belong to the same context are combined into a single LLM call, while
unrelated contexts stay in independent waiting lists. This:

- simplifies the model's job — it gets one well-formed update with the combined content and
  the context's carried state, instead of many fragments;
- keeps the shared local server efficient (fewer, larger calls);
- **naturally separates different clients/streams** — each context is its own queue, so
  multiple speakers/sessions never get merged together.

The queue is transport-agnostic and does no LLM I/O itself; a worker claims a coalesced
batch, runs the actual call, and reports completion.

## Data Contracts

### `LLMRequest` (frozen)

| Field | Type | Meaning |
| --- | --- | --- |
| `context_key` | `str` | Groups related requests; different keys = independent contexts (clients/streams) |
| `sequence` | `int` | Ordering within the context (batches are sorted by this) |
| `payload` | `Any` | The work item (e.g. a `QueuedRawTranscript` section) |
| `depends_on` | `int \| None` | Sequence this request continues, recording intra-context dependency |
| `request_id` | `str` | Stable id (`uuid4` by default) |

Relatedness is expressed by `context_key`: the submitter decides which requests belong
together. `depends_on`/`sequence` record order within a context.

## Coalescing And Dispatch Rules

- Each `context_key` has its own pending list and a single in-flight slot.
- `begin(context_key)` claims **all** currently-pending requests for that context, sorted by
  `sequence`, as one batch, and marks the context in flight.
- While a context is in flight it is not dispatchable; requests submitted meanwhile
  accumulate and are coalesced on the next `begin`.
- `complete(context_key, state=...)` releases the slot and optionally stores carried state
  (e.g. the running transcript / context summary) for the next batch.
- Different contexts are dispatched independently (`dispatchable_contexts()`), so one client
  never blocks another at the queue level.

## Interface

```python
submit(request: LLMRequest) -> None
has_pending(context_key: str | None = None) -> bool
pending_count(context_key: str | None = None) -> int
is_in_flight(context_key: str) -> bool
dispatchable_contexts() -> list[str]
peek(context_key: str) -> LLMRequest | None
begin(context_key: str) -> list[LLMRequest] | None     # claim coalesced batch
complete(context_key: str, state: Any = <unset>) -> None
get_state(context_key) -> Any ; set_state(context_key, state) -> None
clear(context_key: str | None = None) -> None
process_available(handler, can_dispatch=None) -> int   # convenience dispatch loop
```

`process_available(handler, can_dispatch)` dispatches one coalesced batch per ready context:
`handler(context_key, batch, state)` runs the LLM call and returns the new carried state;
`can_dispatch(context_key)` can gate dispatch (e.g. STT priority). The in-flight slot is
always released even if the handler raises.

## Dispatch Lifecycle

```mermaid
sequenceDiagram
    participant P as Producer (STT worker)
    participant Q as LLMRequestQueue
    participant W as Merge worker
    participant LLM

    P->>Q: submit(req ctx=A seq=n)
    Note over Q: pending[A] grows
    W->>Q: dispatch slot? (can_dispatch / STT priority)
    W->>Q: begin("A")
    Q-->>W: coalesced batch (all pending A, ordered)
    Note over Q: A in flight; new submits accumulate
    W->>LLM: one update request (combined content + carried state)
    LLM-->>W: result
    W->>Q: complete("A", state=updated)
    Note over Q: if A has new pending, next begin coalesces again
```

## Use In The Prototype

`PrototypeController` uses one `LLMRequestQueue` for the merge stage. The STT worker
`submit`s each accepted raw transcript section as an `LLMRequest` under a single
`context_key` (the prototype's one mic stream). The merge worker, gated by the STT-priority
slot (`_merge_wait_reason`), `begin`s a coalesced batch and sends it as one cleanup call,
then `complete`s. This is what makes long speech clean up in near-real-time batches rather
than one call per tiny turn. Multiple streams/clients would each use a distinct
`context_key` and be cleaned independently. See
[`voice_prototype.md`](voice_prototype.md) Shared KoboldCPP Scheduling.

## Tests

`tests/test_llm_queue.py` (Layer 1/3):

- pending requests coalesce into one ordered batch,
- unrelated contexts are independent,
- requests accumulate while a context is in flight, then coalesce on the next batch,
- completion carries state for the next batch,
- `peek` does not claim,
- `process_available` dispatches one batch per context, respects `can_dispatch`, and
  releases the slot even if the handler raises.

Integration is exercised by `tests/test_voice_prototype.py` (batching/scheduling).
