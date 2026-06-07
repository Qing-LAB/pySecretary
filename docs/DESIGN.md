# pySecretary Design

This document is the project source of truth. When implementation changes behavior, module boundaries, or external interfaces, update this file in the same change.

## Project Goal

pySecretary is a local voice secretary that listens to a microphone, transcribes speech through KoboldCPP Whisper, organizes the transcript through the local KoboldCPP LLM, and speaks selected responses through KoboldCPP TTS.

The assistant should feel continuous to the user, but the local KoboldCPP Whisper API is request/response. Continuous listening is implemented in the application by buffering microphone audio and sending completed speech turns or short chunks to the transcription endpoint.

## Current External Runtime

- KoboldCPP runs locally at `http://localhost:5001`.
- KoboldCPP exposes OpenAI-compatible endpoints for chat, transcription, and speech.
- KoboldCPP also exposes native `/api/extra/*` endpoints that can be used as fallbacks.
- The current local model reports as `koboldcpp/Qwen_Qwen3.5-9B-Q4_K_M`.

## Design Rules

- Keep one shared KoboldCPP adapter responsible for server discovery, endpoint selection, and request formatting.
- Do not hardcode KoboldCPP endpoint paths in STT, LLM, or TTS modules.
- Keep LLM thoughts separate from spoken output. Anything inside `<think>...</think>` must never be sent to TTS.
- Prefer explicit speech turns over fixed-duration transcription once VAD is implemented.
- Fail visibly but recoverably when local services are unavailable.
- Keep task execution behind a router layer; detection should produce structured intent before any external action is called.

## Module Contracts

### `pysecretary.config`

Owns environment-driven application configuration. It should contain user-tunable defaults only, not endpoint-discovery logic.

Important settings:

- `PSEC_API_BASE`: KoboldCPP base URL.
- `PSEC_API_KEY`: optional local API key.
- `PSEC_STT_MODEL`: model parameter sent to transcription endpoints.
- `PSEC_LLM_MODEL`: model parameter sent to chat endpoints.
- `PSEC_TTS_MODEL`: model parameter sent to speech endpoints.
- `PSEC_TTS_VOICE`: voice name passed to speech endpoints.

### `pysecretary.koboldcpp`

Owns KoboldCPP integration.

Responsibilities:

- Fetch server metadata from `/api/extra/version`.
- Fetch model metadata from `/v1/models` or `/api/v1/model`.
- Pull API documentation from `/api` and extract available routes.
- Select preferred routes for LLM, STT, and TTS.
- Expose stable methods for other modules:
  - `chat_completion(messages, ...)`
  - `transcribe_wav(audio_bytes, ...)`
  - `synthesize_speech(text, ...)`
  - `health()`

Preferred route order:

- LLM: `/v1/chat/completions`, fallback `/api/v1/generate`.
- STT: `/v1/audio/transcriptions`, fallback `/api/extra/transcribe`.
- TTS: `/v1/audio/speech`, fallback `/api/extra/tts`.

### `pysecretary.audio`

Owns microphone capture and playback. The current implementation records fixed segments. The target implementation should add VAD and prevent the assistant from listening while it is speaking.

### `pysecretary.stt`

Owns speech-to-text behavior but delegates endpoint details to `pysecretary.koboldcpp`.

### `pysecretary.llm`

Owns prompts and response shaping but delegates endpoint details to `pysecretary.koboldcpp`.

Required future behavior:

- Strip and separately persist LLM thought traces.
- Prefer structured JSON for task detection.

### `pysecretary.tts`

Owns spoken output behavior but delegates endpoint details to `pysecretary.koboldcpp`.

### `pysecretary.app`

Owns orchestration and state. The target app should move toward a single processing queue with explicit states:

- `listening`
- `processing`
- `speaking`
- `stopped`

## Implementation Phases

### Phase 1: Foundation

- Create the design document.
- Add a KoboldCPP discovery/adapter module.
- Route STT, LLM, and TTS through the shared adapter.
- Add a CLI command for inspecting the discovered KoboldCPP profile.

### Phase 2: Voice Loop

- Replace fixed recording segments with VAD-based speech turns.
- Pause microphone capture during TTS playback.
- Add recoverable error handling for empty speech, HTTP failures, and unavailable devices.

### Phase 3: Thought and Task Handling

- Add a response sanitizer that separates thought traces from final text.
- Convert task detection to structured JSON.
- Add a task router with explicit supported actions.

### Phase 4: Persistent Memory and Review

- Store transcripts, cleaned notes, thought logs, and task results separately.
- Add review/export commands.
- Add tests around parsing, endpoint selection, and task routing.

## Open Questions

- Which local voice should be the default for TTS: `alloy`, `kobo`, or another custom voice?
- Should transcript storage remain plain text, or move to structured JSONL once task routing begins?
- Should the assistant always speak cleaned notes, or only speak confirmations and task results?

