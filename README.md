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

> System libraries (not pip/uv installable): live audio needs **PortAudio** and
> **libsndfile** — `sounddevice`/`soundfile` are only the Python bindings and load these
> native libraries at import. On Debian/Ubuntu/WSL:
>
> ```bash
> sudo apt-get install -y libportaudio2 libsndfile1
> ```
>
> Without them, the app still imports and `--mock` mode works, but microphone capture fails
> with a "PortAudio library not found" message. (WSL note: microphone access needs WSLg /
> a working PulseAudio backend on the Windows side.)

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

### Running on Windows (native)

Live microphone capture is most reliable **natively on Windows** — WSL (especially on
Windows 10) usually cannot pass a microphone through to Linux. On Windows the
`sounddevice`/`soundfile` wheels **bundle PortAudio/libsndfile**, so there is no system-library
step. Use the PowerShell launcher, which installs `uv` if it is missing, creates `.venv`,
installs dependencies, and starts the prototype UI. It uses its own `.venv-win` directory so a
Windows checkout shared with WSL/Linux never collides with the Unix `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-prototype-ui.ps1
powershell -ExecutionPolicy Bypass -File scripts\run-prototype-ui.ps1 --mock     # no mic/server
```

If KoboldCPP is remote, run your SSH tunnel **on Windows** so the forward lands on Windows'
loopback, then point pySecretary at it (PowerShell):

```powershell
# Windows shell: tunnel terminates on Windows localhost
ssh -N -L 5001:localhost:5001 user@remote-linux-host
$env:PSEC_API_BASE = "http://localhost:5001"
```

The first run will trigger a Windows microphone-permission prompt (Settings → Privacy →
Microphone → allow desktop apps). The `.sh` launchers are bash-only; on Windows use the
`.ps1` launcher (or `python -m pysecretary prototype-ui` inside the activated `.venv`).

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
- `scripts/run-tests.sh`: managed test runner; `scripts/run-prototype-ui.sh`: prototype launcher (Linux/macOS/WSL)
- `scripts/run-prototype-ui.ps1`: Windows PowerShell launcher (uv-managed; native mic capture)
- `tests/`: offline module tests, API contract tests, and an opt-in Playwright UI test
- `requirements.txt`: runtime Python dependencies
- `requirements-dev.txt`: dev/test-only dependencies (Playwright)
- `requirements-output.txt`: optional output-bridge deps (pynput/pyperclip) for keystroke/clipboard sinks

## Troubleshooting

- **"PortAudio library not found"** (or a `soundfile`/libsndfile error): install the native
  libraries — `sudo apt-get install -y libportaudio2 libsndfile1`. These are system packages,
  not pip/uv installable. `--mock` mode runs without them.
- **`stage=error:audio_capture` in WSL**: WSL (especially Windows 10) typically does not pass
  a microphone through to Linux, so the capture worker fails even with PortAudio installed.
  Run pySecretary **natively on Windows** with `scripts\run-prototype-ui.ps1` (see *Running on
  Windows*), or use `--mock` in WSL for UI/pipeline testing without a mic. Confirm with
  `python -c "import sounddevice as sd; print(sd.query_devices())"` — no `in`>0 device means WSL
  has no mic source.
- **`/usr/bin/env: 'bash\r'`** on Windows/WSL: the shell scripts were checked out with CRLF.
  Fix with `sudo apt-get install -y dos2unix && dos2unix scripts/*.sh` (or
  `sed -i 's/\r//g' scripts/*.sh`), and set `git config core.autocrlf false`. The committed
  `.gitattributes` keeps `*.sh` as LF on future checkouts. On `/mnt/c`, run scripts with
  `bash scripts/…` (exec bits don't persist) — or clone into the WSL home filesystem.
- If the KoboldCPP server exposes a non-standard endpoint, run `python -m pysecretary inspect-kobold` to see what the adapter discovered.
