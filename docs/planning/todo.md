# Active TODO

This file tracks current work only. Move completed or superseded planning drafts into `docs/planning/archive/`; do not let this list become a historical log.

Status keys:

- `[ ]` pending
- `[~]` in progress
- `[x]` complete
- `[!]` blocked

## Milestone 0: Foundation And Project Memory

- `[x]` Add document-first operating protocol.
- `[x]` Add layered testing strategy.
- `[x]` Add planning directory, roadmap, TODO, and archive policy.
- `[x]` Keep `docs/DESIGN.md` linked to module, deployment, and planning docs.
- `[x]` Keep README linked to source-of-truth docs and test command.
- `[ ]` Commit and push foundation/test/planning updates after review.

## Milestone 1: KoboldCPP Adapter Contract

- `[x]` Add `KoboldCppApi` protocol.
- `[x]` Update STT, LLM, and TTS wrappers to depend on `KoboldCppApi`.
- `[x]` Add offline tests for OpenAI-compatible and native adapter request formatting.
- `[x]` Add deployment guide for local KoboldCPP runtime.
- `[ ]` Run live `python -m pysecretary inspect-kobold` after each KoboldCPP launch script change.

## Milestone 2: Audio Turn Capture

- `[x]` Draft automatic voice smoothing prototype framework.
- `[x]` Add amplitude VAD detector for significant-gap speech turns.
- `[x]` Add prototype controller that can run from fake or microphone turn sources.
- `[x]` Gate no-audio turns before STT requests.
- `[x]` Filter STT non-speech sentinels before raw transcript and LLM merge.
- `[x]` Filter STT audio-caption artifacts before raw transcript and LLM merge.
- `[x]` Strip embedded background sound cues (e.g. "(coughing)") from speech before LLM; LLM backstop too.
- `[x]` Raise default mic sensitivity and keep the pre-STT gate at/below the VAD start threshold.
- `[x]` Make VAD/gate sensitivity tunable at runtime via `UpdateWorkerOption` + dashboard panel.
- `[x]` Stream long speech: flush partial turns with audio overlap (`partial_turn_seconds`/`partial_overlap_seconds`) so STT/cleanup update in near real time.
- `[x]` Stop deferring merge while audio is active; defer only for STT priority so cleanup runs mid-utterance.
- `[x]` Disable model `<think>` generation (`/no_think`) for lower cleanup/summary latency.
- `[ ]` Add a `WorkerSupervisor` abstraction with per-stage supervision/restart (replace ad-hoc completion flags).
- `[x]` Validate repeated-turn capture with STT-priority scheduling and CLI/UI diagnostics in tests.
- `[ ]` Decide whether VAD uses only amplitude/silence threshold first or adds a dedicated dependency.
- `[ ]` Define audio turn capture interface and config fields.
- `[ ]` Implement speech-turn recorder.
- `[ ]` Add tests for silence, speech, max duration, and TTS playback guard.
- `[ ]` Add manual diagnostic command for one-turn record/transcribe.

## Milestone 3: LLM Output Safety And Thought Separation

- `[x]` Isolate dictated raw transcript text from cleanup prompts so instruction-shaped speech is treated as data.
- `[x]` Send ordered section batches with timing metadata to the cleanup model.
- `[x]` Upgrade transcript cleanup to secretary-grade: context-aware grammar/sentence repair and STT-error correction (no summarizing or invented content), with robust topic-switch detection and respect for already-cleaned text.
- `[x]` Add conversation context continuation/renewal metadata for future cleanup turns.
- `[x]` Add LLM context window detection and local prompt overflow guard that preserves latest raw sections.
- `[x]` Implement `<think>...</think>` splitter (`split_thought_text` in `transcript.py`).
- `[x]` Add tests for complete, partial, missing, and malformed thought tags.
- `[x]` Route spoken output through sanitizer before TTS (simple loop `app.py`).
- `[x]` Persist thought traces separately (`thought_log_path`).
- `[x]` Block speech when only thought/empty text remains.
- `[ ]` Define standalone sanitizer module contract if shared beyond `split_thought_text`.
- `[ ]` Route prototype final spoken responses through the same chokepoint once it speaks.

## Milestone 4: App State Machine And Queue

- `[x]` Define prototype event and command contracts.
- `[x]` Add UI-facing reducer state for raw transcript, smoothed transcript, feedback, thoughts, errors, and running status.
- `[x]` Replace sequential prototype loop with queued audio/STT/LLM/UI workers.
- `[x]` Add `audio_turn_queue`, `raw_transcript_queue`, and event relay.
- `[x]` Keep audio capture running while STT and LLM process previous turns.
- `[x]` Emit queue depth/backlog events for UI visibility.
- `[x]` Add Layer 3 tests proving capture can enqueue while STT/LLM are busy.
- `[x]` Prioritize STT over LLM cleanup when both share the same local KoboldCPP server.
- `[x]` Batch accumulated raw transcript sections after each LLM cleanup call returns.
- `[x]` Add a coalescing LLM request queue (`pysecretary.llm_queue`) keyed by context: combine related pending requests into one call; keep unrelated clients/streams independent. Wire the merge stage onto it.
- `[x]` Persist full transcript across context switches (committed history + `prototype_transcript.log`).
- `[x]` Keep main panel focused on current context while sealing prior contexts on renew.
- `[ ]` Define app event and command types.
- `[ ]` Define transcript segment ids and update semantics.
- `[ ]` Implement event reducer/state model.
- `[ ]` Implement queues for audio, transcript merge, analysis, LLM, and TTS work.
- `[ ]` Add cancellation/staleness handling for late worker results.
- `[ ]` Add state transition logging.
- `[ ]` Add recoverable HTTP/audio error handling.
- `[ ]` Add orchestration tests.

## Milestone 5: Lightweight Feedback Dashboard

- `[x]` Add dependency-light prototype dashboard with start/stop controls.
- `[x]` Change thought UI to latest activity plus selected raw-turn detail.
- `[x]` Add responsive in-place CLI audio/status indicator.
- `[x]` Add streaming-style transcript reveal with color coding (settled vs active context).
- `[x]` Add scrollable full-transcript view (committed history + active context).
- `[ ]` Decide lightweight web server runtime: FastAPI/WebSocket vs Flask/Socket.IO.
- `[ ]` Define WebSocket event and command JSON protocol.
- `[x]` Implement dashboard state reducer before browser wiring.
- `[ ]` Implement mock-backend web dashboard.
- `[ ]` Add status strip and processing stage panel.
- `[ ]` Add recording panel with mic level/progress placeholders.
- `[ ]` Add worker options panel for VAD, turn duration, auto-listen, debug mode, TTS voice, and runtime profile.
- `[ ]` Add working transcript panel with segment replacement.
- `[ ]` Add final response/chat panel.
- `[ ]` Add hidden debug/thought panel.
- `[x]` Simplify dashboard to one large auto-scrolling transcript; tuck diagnostics/settings into a collapsed Details section.
- `[x]` Accumulate the full transcript so the whole text is always visible and grows in real time.
- `[x]` Re-editable hot tail (tunable `merge_lookback_sentences`/`merge_lookback_words`): the model may revise the last sentence to fix split-sentence seams; older text is settled/frozen.
- `[x]` Three-way context action (continue / paragraph / renew) so the secretary decides what is settled vs hot, with a compact `context_summary` kept separate from the detailed text.
- `[x]` Add Playwright UI validation (`tests/test_ui_playwright.py`, opt-in via `scripts/run-tests.sh --ui`); dev deps in `requirements-dev.txt`.
- `[ ]` Expand Playwright coverage: controls, sensitivity panel, error/empty states, command routing.

## Milestone 6: Structured Task Detection And Routing

- `[ ]` Define task JSON schema.
- `[ ]` Implement structured task prompt/parser.
- `[ ]` Implement task router skeleton.
- `[ ]` Add tests for valid, invalid, no-task, and unsupported-task outputs.

## Milestone 7: Persistence And Review

- `[ ]` Choose storage format and paths.
- `[ ]` Implement append-only session records.
- `[ ]` Add CLI review/export command.
- `[ ]` Add persistence tests.

## Milestone 8: End-To-End Local Assistant

- `[ ]` Add startup diagnostics.
- `[ ]` Connect UI, audio turns, STT, sanitizer, LLM, task router, TTS, and persistence.
- `[ ]` Write manual end-to-end checklist.
- `[ ]` Update README quickstart from real workflow.

## Milestone 9: Hardening And Packaging

- `[ ]` Add CI workflow for offline tests.
- `[ ]` Decide packaging metadata.
- `[ ]` Add contribution/update process.
