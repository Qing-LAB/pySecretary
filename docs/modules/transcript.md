# Transcript Merge And Thought Separation (`pysecretary.transcript`)

This document is the source of truth for `pysecretary.transcript`. Update it whenever
the thought-splitting rules, the merge-result contract, the merger protocol, or the
JSON parsing rules change.

`pysecretary.transcript` owns two responsibilities:

1. **Thought separation** — split `<think>...</think>` reasoning from user-facing text.
2. **Transcript merging** — turn raw STT sections plus prior state into secretary-grade
   cleaned text (grammar/sentence repair, not verbatim transcription), delegating the
   actual LLM call to [`llm.py`](../DESIGN.md). The controller chooses the editable hot tail
   (via [`context_budget.md`](context_budget.md) `split_recent_tail`) and splices the model's
   region back onto the frozen head — see
   [`voice_prototype.md`](voice_prototype.md) Persistent Full Transcript.

## Data Contracts

### `ThoughtSplit` (frozen)

| Field | Type | Notes |
| --- | --- | --- |
| `final_text` | `str` | User-safe text with thought blocks removed |
| `thoughts` | `list[str]` | Extracted reasoning fragments |

### `TranscriptSection` (frozen)

The unit of raw transcript handed to the merger. Carries provenance/timing so the LLM
can order, stitch, and self-correct. Fields: `turn_id`, `sequence`, `text`,
`captured_at`, `transcribed_at`, `duration_seconds`, `speech_seconds`, `peak_level`.
`to_prompt_dict()` serializes a rounded, model-friendly view.

### `TranscriptMergeResult` (frozen)

| Field | Type | Notes |
| --- | --- | --- |
| `smoothed_text` | `str` | The model's region: on `continue` the corrected hot tail + new sections; on `paragraph`/`renew` only the cleaned new sections |
| `feedback` | `list[str]` | Cleanup notes (UI feedback panel) |
| `thoughts` | `list[str]` | Captured reasoning (debug panel only) |
| `context_summary` | `str` | Compact carry-over for the next merge |
| `context_action` | `str` | `continue`, `paragraph`, or `renew` |

### `TranscriptMerger` (Protocol)

```python
def merge(
    existing_smoothed_text: str,
    new_raw_sections: list[TranscriptSection],
    recent_raw_context: str = "",
    current_context_summary: str = "",
) -> TranscriptMergeResult: ...
```

Implementations: `LLMTranscriptMerger` (production), plus `DemoTranscriptMerger` and
test fakes. The controller depends on the protocol, not a concrete class.

## Thought Splitting Rules

`split_thought_text(text) -> ThoughtSplit`:

- All complete `<think>...</think>` blocks (case-insensitive, dot-all) are removed and
  their inner text collected.
- A trailing **unterminated** `<think>` (truncated/streamed output) is also removed and
  its partial content collected — nothing after an open `<think>` may leak.
- `final_text` is the remaining text, stripped.

This is the single chokepoint used both by the simple app loop ([`app.md`](app.md))
before TTS and by merge-response parsing.

## Merge Response Parsing

`parse_merge_response(response_text)`:

1. Run `split_thought_text` first so reasoning never contaminates parsed output.
2. Try to extract a JSON object (whole string, then the outermost `{...}` slice).
3. On JSON: read `smoothed_text` (or `updated_text`/`text`), `feedback`/`notes`,
   any `thoughts`, `context_summary`, normalized `context_action`.
4. On no JSON: fall back to treating `final_text` as `smoothed_text` (plain-text
   tolerance, as required by the prototype contract).

`context_action` normalizes `renew|new|new_conversation|reset|new_topic` → `renew`,
`paragraph|new_paragraph|new_para|newline|break` → `paragraph`, else `continue`.

## `LLMTranscriptMerger` Flow

```mermaid
sequenceDiagram
    participant C as Controller
    participant M as LLMTranscriptMerger
    participant LLM as LLMClient.merge_transcript_context
    participant P as parse_merge_response

    Note over C: split_recent_tail -> settled head (frozen) + hot tail (editable)
    C->>M: merge(editable_tail, new_sections, recent, summary)
    M->>M: format_transcript_sections_for_prompt(sections) -> JSON
    M->>LLM: merge_transcript_context(editable_tail, new_raw, ...)
    LLM-->>M: response_text (+ context_action)
    M->>P: parse_merge_response(response_text)
    P-->>M: TranscriptMergeResult (region + context_action + context_summary)
    M-->>C: region + context_action
    Note over C: continue -> head + region; paragraph/renew -> current + new paragraph
```

The controller chooses the small editable tail with `split_recent_tail`; the merger passes
it through and returns whatever the model produced. The merger does not own or bound the
full transcript.

## Invariants

- The settled head (everything older than the hot tail) is frozen by the controller and is
  never sent to the model, so it cannot be lost — the transcript never loses settled text.
- On `continue` the model returns the corrected hot tail merged with the new sections; on
  `paragraph`/`renew` it returns only the cleaned new sections. The controller splices
  accordingly (replace tail vs. new paragraph).
- An empty region leaves the transcript unchanged (no data loss).
- `context_summary` (compact topic/entities memory) is maintained separately from the
  detailed text and carried across merges to judge continuity.

## Tests

`tests/test_transcript_merge.py` (Layer 1/2):

- thought split for complete, multiple, and unterminated tags,
- JSON and plain-text merge responses,
- feedback/thought separation,
- empty-output fallback preserves the prior transcript,
- context-guard prefix recombination.
