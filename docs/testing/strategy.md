# Testing Strategy

This document defines pySecretary's test design. Update it whenever test layers, test commands, or validation expectations change.

## Test Command

Offline regression suite:

```bash
python -m unittest discover -s tests
```

Managed runner (creates/syncs the `uv`/`pip` virtual environment, runs the suite with
per-test output buffering, then the compile check). Prefer this to avoid environment
drift between contributors and the prototype launcher:

```bash
scripts/run-tests.sh
```

Compile sanity check:

```bash
python -m compileall pysecretary tests
```

Live integration probes, such as `python -m pysecretary inspect-kobold`, are useful but are not part of the offline regression suite because they depend on the local KoboldCPP runtime.

## Layer 1: API And Data Contracts

Purpose: validate the smallest public contracts and data shapes.

Examples:

- dataclass defaults,
- protocol conformance,
- request payload formatting,
- response parsing,
- serialization/deserialization,
- stable dictionary output,
- config/environment parsing,
- error classes and clear failure behavior.

Expected tests:

- no network,
- no microphone,
- no speaker,
- no GUI,
- deterministic fake inputs.

Current examples:

- `tests/test_config.py`
- `tests/test_koboldcpp.py` profile, context-limit, and payload tests
- `tests/test_events.py`
- `tests/test_transcript_merge.py` thought-split and parse tests
- `tests/test_context_budget.py`
- `tests/test_console.py` status formatter tests
- `tests/test_utils.py`
- future `tests/test_storage.py`

## Layer 2: Module Behavior

Purpose: validate that a module fulfills its documented responsibility using fakes/mocks at its boundaries.

Examples:

- STT wrapper delegates to `KoboldCppApi.transcribe_wav`.
- LLM wrapper delegates to `KoboldCppApi.chat_completion`.
- TTS wrapper delegates to `KoboldCppApi.synthesize_speech`.
- Audio module records/plays through mocked device libraries.
- Sanitizer strips thoughts and returns safe final output.
- Persistence module writes expected records.

Expected tests:

- replace external dependencies with fakes,
- test one module at a time,
- avoid real devices and network,
- assert module-owned behavior rather than collaborator internals.

Current examples:

- `tests/test_module_wrappers.py`
- `tests/test_audio.py`
- `tests/test_audio_vad.py`
- `tests/test_app.py` simple-loop thought-safety, non-speech filtering, task routing
- future `tests/test_sanitizer.py`
- future `tests/test_task_router.py`

## Layer 3: Protocol, Communication, And Inter-Module Behavior

Purpose: validate that modules communicate correctly through documented protocols and that multi-step workflows preserve state and safety constraints.

Examples:

- event reducer updates UI-facing state from events,
- transcript segment updates replace by stable id,
- cancellation prevents stale worker results from overwriting current state,
- thought events do not enter final response or TTS paths,
- controller routes commands to workers,
- app state transitions are deterministic,
- task detection feeds the router only after schema validation.

Expected tests:

- use fake workers and event queues,
- validate event/command contracts,
- validate state transitions,
- validate cross-module safety rules,
- stay offline and deterministic.

Current examples:

- `tests/test_voice_prototype.py` controller pipeline, scheduling, and staleness
- `tests/test_events.py` reducer state transitions and thought/feedback separation
- `tests/test_app.py` simple-loop end-to-end thought safety and task path

Future examples:

- `tests/test_controller.py`
- `tests/test_ui_state.py`
- `tests/test_pipeline.py`
- future Playwright tests using fake backend events

## Layer 4: Live Local Integration Checks

Purpose: validate deployment compatibility with the actual local KoboldCPP runtime.

These checks are manual or explicitly invoked diagnostics, not default offline tests.

Examples:

- `python -m pysecretary inspect-kobold`
- STT request against a known WAV file.
- TTS request writing a WAV file.
- one-turn record/transcribe diagnostic.
- full assistant manual checklist.

Expected behavior:

- document prerequisites in deployment docs,
- do not require these checks for normal unit test runs,
- record failures as deployment or integration issues before changing core code.

## Test Design Rules

- Write tests from the design contract, not from incidental implementation details.
- Add Layer 1 tests before or with a new public API.
- Add Layer 2 tests before or with a new module.
- Add Layer 3 tests before connecting parallel workers, UI event streams, or controller logic.
- Use fakes for KoboldCPP, audio devices, GUI, and external services in offline tests.
- Test the UI state reducer and event/command protocol before browser-level Playwright tests.
- Keep live integration probes separate from the offline suite.
- If a bug crosses module boundaries, add a Layer 3 regression test.
- If a deployment mismatch causes a bug, update deployment docs and adapter tests together.
