# pySecretary Roadmap

This is the active milestone plan. Keep it current as work lands. Completed or superseded planning drafts belong in `docs/planning/archive/`.

## Goal

Build a local voice secretary that continuously listens through a microphone, transcribes completed speech turns through local KoboldCPP Whisper, organizes and routes requests through local KoboldCPP LLM, speaks safe final responses through local KoboldCPP TTS, and persists useful transcripts/tasks without leaking model thoughts.

## Immediate Next Milestone: Real-Time UI Validation And Pipeline Hardening

Status: in progress

The prototype now streams a single growing transcript (settled head + re-editable hot tail) with a simplified
dashboard, runtime-tunable sensitivity, background-cue filtering, and `/no_think` low-latency
cleanup. The next milestone makes that experience trustworthy and maintainable:

- **Browser validation (Playwright):** the first dashboard UI test exists
  (`tests/test_ui_playwright.py`, run via `scripts/run-tests.sh --ui`, deps in
  `requirements-dev.txt`). Expand to cover controls (start/stop/clear), the sensitivity
  panel + `UpdateWorkerOption`, error/empty states, and real-time growth across many turns.
- **Architecture hardening:** introduce a `WorkerSupervisor` that owns the start/stop/join
  lifecycle and per-stage health uniformly (replacing ad-hoc completion flags), so new
  stages (analysis, TTS) compose cleanly. See
  [`../modules/voice_prototype.md`](../modules/voice_prototype.md) Worker Lifecycle.
- **CI:** run the offline suite on push; optionally the Playwright job with a cached browser.

Acceptance: dashboard behavior (transcript grows, full text visible, controls + options
work, thoughts never shown as final) is verified by Playwright; the pipeline lifecycle is
supervised; CI runs the offline suite.

## Milestone 0: Foundation And Project Memory

Status: in progress

Purpose: establish source-of-truth docs, tests, repository hygiene, and the first stable integration module.

Deliverables:

- Source-of-truth design doc.
- Document-first operating protocol.
- Layered testing strategy.
- KoboldCPP adapter design doc.
- KoboldCPP deployment guide.
- Planning directory with roadmap, TODO list, and archive policy.
- Offline test suite.
- Public GitHub repository.

Acceptance Criteria:

- `docs/DESIGN.md` describes top-level architecture and points to module/deployment/planning docs.
- `docs/planning/protocol.md` defines the required document-first workflow.
- `docs/testing/strategy.md` defines Layer 1, Layer 2, and Layer 3 test expectations.
- `docs/modules/koboldcpp.md` defines the first module interface and tests.
- `docs/deployment/koboldcpp.md` defines the runtime contract for the local KoboldCPP server.
- `docs/planning/README.md`, `docs/planning/roadmap.md`, and `docs/planning/todo.md` exist.
- `python -m unittest discover -s tests` passes.
- `python -m compileall pysecretary tests` passes.
- Git repo has a clean commit pushed to GitHub after this milestone is closed.

## Milestone 1: KoboldCPP Adapter Contract

Status: in progress

Purpose: finish the first production-quality module boundary for all KoboldCPP calls.

Deliverables:

- `KoboldCppApi` protocol.
- `KoboldCppProfile` diagnostics contract.
- Discovery of version, capabilities, routes, and model id.
- OpenAI-compatible and native fallback support for LLM, STT, and TTS.
- Offline tests for endpoint selection, request formatting, and errors.
- Live inspection command: `python -m pysecretary inspect-kobold`.

Acceptance Criteria:

- `KoboldCppClient` satisfies `KoboldCppApi`.
- STT, LLM, and TTS modules depend on `KoboldCppApi`, not direct HTTP calls.
- OpenAI-compatible routes are preferred when available.
- Native routes are selected when OpenAI-compatible routes are missing.
- Missing required capability produces an unavailable endpoint and clear error.
- `python -m pysecretary inspect-kobold` reports healthy local runtime on `127.0.0.1:5001` or `localhost:5001`.
- Unit tests cover both route styles and pass offline.

## Milestone 2: Audio Turn Capture

Status: pending

Purpose: replace fixed-time microphone capture with speech-turn capture that feels continuous while respecting KoboldCPP Whisper's request/response API.

Deliverables:

- Prototype amplitude VAD detector for significant-gap speech turns.
- Audio capture interface for speech turns.
- Voice activity detection or silence-threshold turn detection.
- Configurable sample rate, chunk size, silence duration, max turn duration, and energy threshold.
- A guard that prevents recording while TTS playback is active.
- Unit tests using mocked audio dependencies.
- Manual diagnostic command for recording/transcribing one turn.

Acceptance Criteria:

- Empty room silence does not continuously call STT.
- A spoken phrase produces one WAV turn and one STT request.
- Long speech is capped or split predictably.
- TTS playback does not feed back into microphone capture inside the app loop.
- Audio tests run without a physical microphone or speaker.
- Manual diagnostic can record a turn and print transcript through KoboldCPP.

## Milestone 3: LLM Output Safety And Thought Separation

Status: in progress

Purpose: ensure text spoken by pySecretary never contains hidden reasoning or `<think>` traces.

Progress: `split_thought_text` (`pysecretary.transcript`, see
[`../modules/transcript.md`](../modules/transcript.md)) implements the complete and
unterminated `<think>` splitter. The simple voice loop (`pysecretary.app`, see
[`../modules/app.md`](../modules/app.md)) now sanitizes before TTS, persists thoughts to
a separate log, and blocks thought-only speech, with regression tests in
`tests/test_app.py`. Remaining: a standalone sanitizer module contract if the simple
loop and prototype need to share more than `split_thought_text`, and routing the
prototype's final spoken responses through the same chokepoint once it speaks.

Deliverables:

- Response sanitizer module.
- Thought/final-output split for common tags such as `<think>...</think>`.
- Thought log persistence separate from spoken output.
- Tests for complete, partial, missing, and malformed thought tags.
- LLM prompt updates that request final-only output where possible.

Acceptance Criteria:

- TTS receives final/safe text only.
- Thought traces are stored separately when present.
- If a response contains only thought text or incomplete thought text, spoken output is blocked or replaced with a safe fallback.
- Sanitizer tests cover Qwen-style `<think>` output observed locally.

## Milestone 4: App State Machine And Queue

Status: pending

Purpose: make orchestration reliable by replacing concurrent ad hoc calls with an event/command pipeline that supports parallel work and feedback control.

Deliverables:

- Prototype event/command contracts and UI-facing reducer state.
- Explicit states: `listening`, `processing`, `speaking`, `stopped`.
- Event and command types for backend/UI communication.
- Separate audio capture, STT, LLM merge, and UI event relay workers.
- Processing queues for audio turns, transcript updates, analysis, LLM generation, and TTS.
- Queue depth/backlog events for UI visibility.
- Stable ids for transcript segments so text can be updated or replaced instead of only appended.
- Cancellation/staleness handling so late worker results cannot overwrite newer state.
- Graceful stop behavior.
- Recoverable error handling around STT, LLM, TTS, and device failures.
- Debug logging for state transitions.
- Tests for state transitions and error recovery.

Acceptance Criteria:

- Console commands and audio turns cannot race the same LLM/TTS pipeline.
- Microphone capture continues while previous speech turns are being transcribed or merged.
- Parallel transcription, analysis, and TTS work report progress through events.
- Tests prove that multiple captured turns can queue while STT/LLM workers are busy.
- The app can revise a working transcript segment by id.
- UI-facing state can be reconstructed from events.
- Cancellation prevents stale work from updating current state.
- Ctrl+C or `stop` exits cleanly.
- A failed STT/LLM/TTS call does not kill the assistant loop.
- Tests prove expected state transitions for success and failure paths.

## Milestone 5: Lightweight Feedback Dashboard

Status: pending

Purpose: provide a lightweight local web dashboard that visualizes continuous recording, parallel processing, worker status, option changes, working transcript updates, final safe responses, and debug/thought separation. The dashboard is a control surface over the backend worker/controller system, not the owner of assistant logic.

Deliverables:

- UI design doc.
- Event reducer/state model that is testable without a browser.
- Dependency-light prototype dashboard using server-sent events plus HTTP command posts.
- Lightweight local web dashboard with status strip, recording panel, worker options panel, working transcript panel, final chat panel, processing panel, and debug/thought panel.
- WebSocket event and command JSON protocol.
- Mock backend event playback for dashboard development.
- User commands for listen/pause/resume/cancel/manual text/debug toggle and worker option updates.
- Tests for state reducer, transcript segment replacement, thought separation, command routing, worker option commands, and browser behavior through fake events.

Acceptance Criteria:

- Dashboard can render fake backend events without KoboldCPP or audio devices.
- Recording progress and mic level updates are visible from events.
- Working transcript can update an existing segment instead of appending duplicates.
- Final response panel never includes thought events.
- Debug panel can show thought events when enabled.
- Dashboard controls emit commands to the app controller boundary.
- Worker option controls emit command messages and do not mutate worker internals directly.
- Backend worker/controller logic and CLI diagnostics remain usable without opening the dashboard.

## Milestone 6: Structured Task Detection And Routing

Status: pending

Purpose: turn cleaned text into structured intents before taking action.

Deliverables:

- JSON task schema.
- Prompt layer for structured task detection.
- Parser and validator for model-produced JSON.
- Task router with explicit supported actions.
- Safe fallback when intent is unknown or malformed.
- Tests for task extraction, no-task cases, malformed JSON, and router decisions.

Acceptance Criteria:

- Task detection returns typed data, not free-form text.
- No external action is called unless the task schema validates.
- Unknown tasks are summarized safely.
- Tests cover no-task, single-task, malformed, and unsupported-task cases.

## Milestone 7: Persistence And Review

Status: pending

Purpose: store assistant outputs in a durable, reviewable structure.

Deliverables:

- Structured storage format, likely JSONL.
- Separate records for raw transcript, cleaned text, thought traces, spoken output, and task results.
- Configurable storage paths.
- CLI commands for listing and exporting recent sessions.
- Tests for storage writes and reads.

Acceptance Criteria:

- Session history can be inspected without parsing console output.
- Thought logs are physically separate from spoken text.
- Storage handles multiple sessions without overwriting.
- Tests verify record shape and append behavior.

## Milestone 8: End-To-End Local Assistant

Status: pending

Purpose: make the app usable as a local voice secretary.

Deliverables:

- Full voice loop using Milestones 2-6.
- Startup diagnostics that report KoboldCPP health and selected endpoints.
- Clear CLI commands for running, inspecting KoboldCPP, testing audio, and reviewing history.
- README quickstart updated from real workflow.
- Manual end-to-end checklist.

Acceptance Criteria:

- Starting pySecretary checks KoboldCPP before entering the voice loop.
- A spoken instruction can be transcribed, cleaned, safely spoken, and persisted.
- A task-like request can be detected and routed or safely deferred.
- End-to-end manual checklist passes on the known local KoboldCPP deployment.

## Milestone 9: Hardening And Packaging

Status: pending

Purpose: prepare the project for repeated use and contribution.

Deliverables:

- Packaging metadata if needed.
- Optional `pytest` migration or continued `unittest` standard.
- CI workflow for offline tests.
- More precise type checks if dependencies permit.
- Contribution/update process for docs and planning.

Acceptance Criteria:

- Fresh clone can install dependencies and run tests from README.
- CI runs offline tests successfully.
- Public docs explain deployment, architecture, planning, and testing.
