# Lightweight UI And Streaming Feedback Design

This document is the source of truth for pySecretary's user interface and realtime feedback behavior. Update it whenever UI state, event flow, concurrency, or streaming transcript behavior changes.

## Purpose

The UI is a lightweight visual feedback and control surface for a backend-driven local assistant. It should show recording progress, evolving transcript text, background processing status, final assistant output, and debug/thought traces without letting thought text contaminate final visible or spoken responses.

The backend, hardware integration, CLI diagnostics, worker orchestration, event bus, and persistence are more important than the UI. The UI must not become the owner of assistant logic.

The UI should be optional. The backend worker/controller layer and CLI diagnostics must remain usable without opening a browser.

## Core Requirement

pySecretary should feel continuous even though the local KoboldCPP Whisper endpoint is request/response. The app should support overlapping work:

- capture audio continuously,
- segment speech into turns or partial chunks,
- transcribe chunks,
- merge partial transcripts into a working user text,
- analyze context while more audio is arriving,
- revise the working text when better context arrives,
- generate final summaries/responses,
- keep thought/debug text separated from final output,
- provide feedback/control signals to pause, resume, cancel, retry, or revise.

The UI must therefore support updates, replacements, and corrections, not just append-only chat messages.

## Recommended Interface Layer

The UI should not call KoboldCPP, audio devices, or LLM prompts directly. It should subscribe to an application event stream and send user control commands or option updates back to the app controller.

The CLI should use the same backend/controller concepts where practical. UI and CLI are both control surfaces over the same worker system.

Primary objects:

- `AssistantEvent`: immutable event emitted by backend/controller.
- `AssistantCommand`: command emitted by UI/user controls.
- `TranscriptSegment`: editable unit of user text with stable id and status.
- `AssistantState`: current UI-facing state snapshot.

## Recommended UI Technology

Use a lightweight local web dashboard rather than a heavy desktop or SPA framework.

Recommended first implementation:

- Python backend server exposing static HTML/CSS/JS.
- WebSocket endpoint for event and command messages.
- Vanilla JavaScript reducer for UI state.
- Playwright tests for browser behavior using fake backend events.
- No heavy single-page application framework unless a later milestone proves it is needed.

The UI should be simple enough to inspect and test:

```text
pysecretary/web/
├── server.py
└── static/
    ├── index.html
    ├── app.js
    └── styles.css
```

The exact backend server choice can be finalized when implementation begins. Prefer a server that handles WebSockets cleanly and does not complicate worker orchestration. FastAPI plus WebSocket is the preferred direction; Flask plus Socket.IO is acceptable if we choose Flask for other reasons.

The automatic voice smoothing prototype may temporarily use server-sent events for backend-to-browser updates and HTTP `POST` for commands. This keeps the first dashboard dependency-light while preserving the event/command payload shape.

Browser microphone capture is not the first design target. The Python backend should own microphone/speaker hardware initially, because local hardware integration and CLI diagnostics are core project requirements.

## Concurrency Model

The UI should render state from backend events. Background work should not mutate UI state directly.

The backend must not model continuous voice interaction as `record -> transcribe -> clean -> record again`. Audio capture should continue while previous turns are being transcribed and merged.

Recommended architecture:

- Browser UI: renders state and sends commands/option updates.
- App controller: owns state machine and event routing.
- Audio capture worker: emits audio-level, speech-start, partial-turn, and turn-complete events.
- STT worker: transcribes completed chunks/turns.
- Analysis worker: incrementally analyzes merged user text and context.
- LLM worker: generates final/safe assistant responses.
- TTS worker: synthesizes and plays final output.

Minimum queue flow for the voice smoothing prototype:

```text
audio capture worker -> audio_turn_queue -> STT worker -> raw_transcript_queue -> LLM merge worker -> event_queue -> UI relay
```

The UI should surface queue/backlog status so the user can see when STT or LLM cleanup is behind live capture.

The terminal should provide the same basic runtime confidence signal when the local server is run interactively: a single in-place line showing audio detected/quiet, level, VAD turn state, queue depths, and processing stage. It should not print a new line per chunk.

The core should communicate through queues/events, not through direct shared-state mutation.

Threads or subprocesses may be used as implementation details for blocking libraries such as `sounddevice`, `requests`, or TTS playback, but the design should not depend on ad hoc shared-state threading. Prefer:

- event queues,
- WebSocket delivery for UI events,
- worker objects with clear ownership,
- cancellation tokens or command messages,
- immutable event payloads.

If `asyncio` is introduced later, it should remain behind the app controller boundary so the UI/CLI command contract does not change.

## UI Layout

Recommended first dashboard:

- Header/status strip:
  - KoboldCPP connection status.
  - selected LLM/STT/TTS endpoint styles.
  - current assistant state.
  - queue/backlog indicator.

- Recording panel:
  - mic level meter.
  - recording timer.
  - VAD/silence status.
  - push-to-talk control.
  - auto-listen toggle.
  - pause/resume/cancel controls.

- Worker options panel:
  - VAD/silence threshold controls.
  - max turn duration.
  - auto-listen toggle.
  - debug/thought visibility toggle.
  - TTS voice selector when supported.
  - KoboldCPP endpoint/profile status.

- Working transcript panel:
  - displays evolving user text.
  - supports segment statuses: `recording`, `transcribing`, `tentative`, `revised`, `final`.
  - allows later updates to replace or merge earlier text.
  - streaming feedback: the transcript is one large, auto-scrolling panel; the newly
    appended tail is briefly highlighted as it updates, with a blinking cursor while capture
    is running, so the user can track live progress.
  - the full transcript (`smoothed_text`) is always visible; the settled part only grows and
    the recent hot tail may re-flow as it is refined;
    diagnostics and settings live in a collapsed "Details" section so the main view stays
    focused on the text. See [`voice_prototype.md`](voice_prototype.md) Persistent Full
    Transcript for the data model.

- Chat/final output panel:
  - user finalized turns.
  - assistant final responses.
  - task result messages.

- Processing panel:
  - shows current background stages:
    - recording,
    - transcribing,
    - merging,
    - analyzing,
    - generating,
    - speaking.

- Debug/thought panel:
  - hidden or collapsed by default.
  - shows separated thought traces only when debug mode is enabled.
  - never feeds into the final output or TTS path.

## Event Types

Initial event set:

- `KoboldProfileDiscovered`
- `AssistantStateChanged`
- `QueueDepthChanged`
- `AudioLevelChanged`
- `RecordingStarted`
- `RecordingProgress`
- `RecordingStopped`
- `SpeechTurnStarted`
- `SpeechTurnCompleted`
- `TranscriptionStarted`
- `TranscriptSegmentCreated`
- `TranscriptSegmentUpdated`
- `TranscriptSegmentFinalized`
- `TranscriptMergeStarted`
- `TranscriptMergeCompleted`
- `AnalysisStarted`
- `AnalysisProgress`
- `AnalysisCompleted`
- `ThoughtCaptured`
- `FinalResponseStarted`
- `FinalResponseReady`
- `TtsStarted`
- `TtsCompleted`
- `AssistantError`

Events that update text must include stable ids so the UI can update existing content instead of appending duplicates.

## Command Types

Initial command set:

- `StartListening`
- `PauseListening`
- `ResumeListening`
- `StopListening`
- `StartPushToTalk`
- `EndPushToTalk`
- `CancelCurrentTurn`
- `RetryLastStep`
- `SubmitManualText`
- `ToggleDebugPanel`
- `ClearWorkingTranscript`
- `UpdateWorkerOption`

Commands should be accepted by the app controller, not individual widgets.

## Transcript Merge Rules

The working transcript is made of segments. Each segment has:

- stable id,
- raw text,
- cleaned/revised text,
- time range if known,
- status,
- source: `stt`, `manual`, or `system`,
- confidence/quality metadata if available.

Merge behavior:

- Partial STT output may create tentative segments.
- Later STT or LLM cleanup may update the same segment id.
- Context analysis may propose replacements, but finalization should be explicit.
- Final user text should preserve enough provenance to audit what changed.

## Thought Safety

The UI may display thought traces only in the debug/thought panel.

Forbidden:

- thought text in final assistant response panel,
- thought text in spoken TTS output,
- thought text stored as normal user/assistant conversation text.

Required:

- sanitized final output before TTS,
- separate thought events,
- tests proving contamination cannot cross into final output.

## Test Requirements

The UI/concurrency layer must be testable without a real GUI, microphone, speaker, or KoboldCPP server.

Required tests:

- event reducer updates assistant state deterministically,
- transcript segment updates replace existing segment by id,
- final output ignores thought events,
- debug panel state can include thought events when enabled,
- commands are routed to app controller,
- worker option changes emit commands without directly changing worker internals,
- background worker results emit events rather than mutating UI directly,
- cancellation command prevents stale results from overwriting newer state.

Playwright tests can be added after the reducer and WebSocket protocol exist. The state/event reducer should be tested before browser wiring.
