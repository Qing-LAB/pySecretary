# pySecretary

A Python-based voice assistant and secretary application that continuously listens to microphone input, converts speech to text, cleans and organizes the transcript using a local LLM, and converts final results back to speech. The LLM stores its thought traces separately from spoken output.

Project design lives in [`docs/DESIGN.md`](docs/DESIGN.md). Update that file whenever feature scope, architecture, or external interface behavior changes.

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
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables:

```bash
export PSEC_API_BASE="http://localhost:5001"
export PSEC_API_KEY=""
export PSEC_STT_MODEL="kcpp"
export PSEC_LLM_MODEL="kcpp"
export PSEC_TTS_MODEL="kcpp"
export PSEC_SEGMENT_SECONDS="6"
```

4. Inspect the local KoboldCPP API profile:

```bash
python -m pysecretary inspect-kobold
```

5. Run the assistant:

```bash
python -m pysecretary
```

## Notes

- The assistant tries to avoid converting the LLM's internal thought process into speech. It only speaks the final organized output or task results.
- If the LLM detects a task request, it can optionally call an external service for more complex operations. The `external_api_call` stub in `pysecretary/app.py` shows where to extend that logic.

## File structure

- `pysecretary/`: main package
- `pysecretary/app.py`: orchestrates audio, STT, LLM, and TTS
- `pysecretary/koboldcpp.py`: discovers KoboldCPP capabilities and exposes shared API calls
- `pysecretary/audio.py`: microphone capture helper
- `pysecretary/stt.py`: speech-to-text client
- `pysecretary/llm.py`: LLM client and prompt layer
- `pysecretary/tts.py`: text-to-speech client and playback
- `pysecretary/config.py`: environment-driven configuration
- `docs/DESIGN.md`: source-of-truth design and implementation contract
- `requirements.txt`: Python dependencies

## Troubleshooting

- On Linux, you may need PortAudio system libraries for `sounddevice`.
- If the KoboldCPP server exposes a non-standard endpoint, run `python -m pysecretary inspect-kobold` to see what the adapter discovered.
