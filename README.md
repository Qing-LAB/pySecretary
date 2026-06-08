# pySecretary

A Python-based voice assistant and secretary application that continuously listens to microphone input, converts speech to text, cleans and organizes the transcript using a local LLM, and converts final results back to speech. The LLM stores its thought traces separately from spoken output.

Project design lives in [`docs/DESIGN.md`](docs/DESIGN.md). Update that file whenever feature scope, architecture, or external interface behavior changes.

Active planning lives in [`docs/planning/`](docs/planning/).

All implementation work follows [`docs/planning/protocol.md`](docs/planning/protocol.md). Test design follows [`docs/testing/strategy.md`](docs/testing/strategy.md).

## Features

- Continuous microphone monitoring
- Speech-to-text using a local KoboldCPP Whisper endpoint
- LLM text organization and task extraction using a local KoboldCPP LLM endpoint
- Text-to-speech output using a local KoboldCPP Kokoro endpoint
- Separate thought logs and final voice output
- Task detection for follow-up actions

## Setup

1. Create a virtual environment:

```bash
uv venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
uv pip install -r requirements.txt
```

If `uv` is unavailable on another machine, `python -m venv .venv` and `pip install -r requirements.txt` remain valid fallbacks.

3. Configure environment variables:

```bash
export PSEC_API_BASE="http://localhost:5001"
export PSEC_API_KEY=""
export PSEC_STT_MODEL="kcpp"
export PSEC_LLM_MODEL="kcpp"
export PSEC_TTS_MODEL="kcpp"
export PSEC_SEGMENT_SECONDS="7"
```

4. Inspect the local KoboldCPP API profile:

```bash
python -m pysecretary inspect-kobold
```

5. Run the assistant:

```bash
python -m pysecretary
```

6. Run the automatic voice smoothing prototype UI:

```bash
python -m pysecretary prototype-ui
```

For dashboard-only testing without live microphone or KoboldCPP calls:

```bash
python -m pysecretary prototype-ui --mock
```

The helper script creates/uses `.venv`, installs dependencies with `uv` when available, and starts the prototype UI:

```bash
scripts/run-prototype-ui.sh --mock
```

If the default port `8765` is busy, the helper script automatically chooses the next free port unless you pass `--port` explicitly.

## Tests

Run the offline regression suite:

```bash
python -m unittest discover -s tests
```

Or use the managed runner (creates/syncs the `uv` environment, then runs tests + a compile
check). Add `--ui` to also install Playwright + a browser and run the dashboard UI test:

```bash
scripts/run-tests.sh           # offline suite
scripts/run-tests.sh --ui      # + browser UI validation
```

## Notes

- The assistant tries to avoid converting the LLM's internal thought process into speech. It only speaks the final organized output or task results.
- If the LLM detects a task request, it can optionally call an external service for more complex operations. The `external_api_call` stub in `pysecretary/app.py` shows where to extend that logic.

## File structure

- `pysecretary/`: main package
- `pysecretary/app.py`: simple synchronous voice loop (record/transcribe/clean/speak)
- `pysecretary/prototype.py`: event-driven automatic voice smoothing prototype controller
- `pysecretary/events.py`: UI-facing event, command, and prototype state contracts
- `pysecretary/transcript.py`: transcript merge parsing and thought separation helpers
- `pysecretary/llm_queue.py`: coalescing LLM request queue (combines related requests; separates clients)
- `pysecretary/output_bridge.py`: send finalized text to other programs (stdout/clipboard/keystroke; push-to-send)
- `pysecretary/context_budget.py`: prompt context-window budgeting for transcript merge
- `pysecretary/console.py`: in-place one-line CLI status indicator
- `pysecretary/koboldcpp.py`: discovers KoboldCPP capabilities and exposes shared API calls
- `pysecretary/audio.py`: microphone capture helper
- `pysecretary/stt.py`: speech-to-text client
- `pysecretary/llm.py`: LLM client and prompt layer
- `pysecretary/tts.py`: text-to-speech client and playback
- `pysecretary/config.py`: environment-driven configuration
- `pysecretary/web/`: dependency-light local dashboard for prototypes
- `docs/DESIGN.md`: source-of-truth design and implementation contract
- `docs/deployment/koboldcpp.md`: KoboldCPP runtime setup and validation guide
- `docs/modules/koboldcpp.md`: KoboldCPP adapter module contract and test design
- `docs/modules/app.md`: simple synchronous voice loop contract
- `docs/modules/voice_prototype.md`: automatic voice smoothing prototype contract
- `docs/modules/events.md`: event/command/state data contracts and reducer
- `docs/modules/transcript.md`: thought separation and transcript merge contract
- `docs/modules/llm_queue.md`: coalescing LLM request queue contract
- `docs/modules/context_budget.md`: prompt context-window budgeting contract
- `docs/modules/console.md`: CLI status indicator contract
- `docs/modules/output_bridge.md`: send finalized text to other programs (stdout/clipboard/keystroke)
- `docs/modules/ui.md`: lightweight UI dashboard, streaming feedback, and concurrency design
- `docs/planning/`: active roadmap, TODO list, and archive policy
- `docs/testing/strategy.md`: layered testing strategy
- `scripts/run-tests.sh`: managed test runner; `scripts/run-prototype-ui.sh`: prototype launcher
- `tests/`: offline module tests, API contract tests, and an opt-in Playwright UI test
- `requirements.txt`: runtime Python dependencies
- `requirements-dev.txt`: dev/test-only dependencies (Playwright)
- `requirements-output.txt`: optional output-bridge deps (pynput/pyperclip) for keystroke/clipboard sinks

## Troubleshooting

- On Linux, you may need PortAudio system libraries for `sounddevice`.
- If the KoboldCPP server exposes a non-standard endpoint, run `python -m pysecretary inspect-kobold` to see what the adapter discovered.
