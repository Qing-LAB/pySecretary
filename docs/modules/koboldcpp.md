# KoboldCPP Adapter Design

This document is the source of truth for `pysecretary.koboldcpp`. Update it whenever the adapter contract, endpoint selection rules, request payloads, or response parsing change.

Deployment guidance for running KoboldCPP to satisfy this contract lives in [`docs/deployment/koboldcpp.md`](../deployment/koboldcpp.md).

## Purpose

`pysecretary.koboldcpp` is the only module that should know how to talk to KoboldCPP HTTP endpoints. Other modules should depend on its public interface and should not hardcode KoboldCPP paths, payload shapes, response parsing, or fallback rules.

## Runtime Assumptions

- KoboldCPP is local by default at `http://localhost:5001`.
- The server may expose OpenAI-compatible routes, native KoboldCPP routes, or both.
- Local Whisper transcription is request/response, not true continuous streaming.
- Local TTS returns WAV bytes when available.
- The currently observed KoboldCPP server exposes:
  - `/api/extra/version`
  - `/api`
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/audio/transcriptions`
  - `/v1/audio/speech`
  - `/api/v1/generate`
  - `/api/extra/transcribe`
  - `/api/extra/tts`

## Public Interface

Downstream modules should type against `KoboldCppApi`, not raw HTTP calls.

Required methods:

```python
chat_completion(
    messages: list[dict[str, str]],
    model: str = "kcpp",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    **extra: Any,
) -> dict[str, Any]

transcribe_wav(
    audio_bytes: bytes,
    model: str = "kcpp",
    prompt: str = "",
    language: str = "en",
    suppress_non_speech: bool = False,
) -> str

synthesize_speech(
    text: str,
    model: str = "kcpp",
    voice: str = "alloy",
    instruction: str = "",
    speaker_json: str | None = None,
) -> bytes

health() -> dict[str, Any]

refresh_profile() -> KoboldCppProfile
```

## Data Contracts

### `KoboldCppProfile`

The profile records the discovered server state and selected adapter routes.

Required fields:

- `api_base`: normalized base URL without trailing slash.
- `version`: KoboldCPP version if reported.
- `model_id`: current model id if reported.
- `context_limit_tokens`: detected model context-window size, or `None` if it cannot be
  determined. Consumed by the merge context guard
  ([`context_budget.md`](context_budget.md)).
- `protected`: whether KoboldCPP reports protected mode.
- `capabilities`: boolean feature flags from `/api/extra/version`, excluding metadata fields.
- `routes`: discovered route paths.
- `llm_style`, `llm_endpoint`: selected LLM route.
- `stt_style`, `stt_endpoint`: selected transcription route.
- `tts_style`, `tts_endpoint`: selected speech route.

`to_dict()` must return stable, sorted capabilities and routes for CLI output and
diagnostics, and includes `context_limit_tokens`.

## Discovery Rules

Discovery should:

1. Fetch `/api/extra/version`.
2. Fetch routes from `/openapi.json`, `/swagger.json`, or `/api`.
3. Fetch model id from `/v1/models`, falling back to `/api/v1/model`.
4. Detect the context-window limit from runtime metadata (see below).
5. Select endpoints with the route preferences below.

### Context-window detection

Probe these sources and take the largest credible value (`>= 512`):

- model metadata already fetched (`/v1/models` entries),
- `/api/extra/true_max_context_length` (`result`/`value`/`max_context_length`),
- `/api/v1/config`, `/api/extra/config`, `/props`.

Detection walks nested JSON for context-size keys (normalized, ignoring case and
non-alphanumerics): `context_size`, `context_length`, `context_limit`,
`context_window`, `max_context*`, `n_ctx`, `n_ctx_train`, `true_max_context_length`.
If nothing credible is found, `context_limit_tokens` is `None` and consumers fall back
to `config.llm_context_window_tokens`. All probes are optional: failures must not raise.

Preferred route order:

- LLM: `/v1/chat/completions`, fallback `/api/v1/generate`.
- STT: `/v1/audio/transcriptions`, fallback `/api/extra/transcribe`.
- TTS: `/v1/audio/speech`, fallback `/api/extra/tts`.

If route metadata cannot be fetched but the required capability is not explicitly disabled, the adapter may optimistically use the preferred OpenAI-compatible route.

## Request Formatting

### Chat

OpenAI-compatible route:

- POST JSON to `/v1/chat/completions`.
- Include `model`, `messages`, `temperature`, optional `max_tokens`, and extra sampler fields.
- Return the server JSON unchanged.

Native route:

- POST JSON to `/api/v1/generate`.
- Convert chat messages to a text prompt.
- Include `prompt`, `temperature`, `max_length`, and `quiet`.
- Convert native text output into an OpenAI-like chat response shape.

### Transcription

OpenAI-compatible route:

- POST multipart form data to `/v1/audio/transcriptions`.
- Include file tuple `("recording.wav", audio_bytes, "audio/wav")`.
- Include `model`, `prompt`, and `language`.
- Return the parsed text from `text`, `transcription`, or `result`.

Native route:

- POST JSON to `/api/extra/transcribe`.
- Include base64 WAV in `audio_data`.
- Include `prompt`, `langcode`, and `suppress_non_speech`.
- Return the parsed text from `text`, `transcription`, or `result`.

### Speech

OpenAI-compatible route:

- POST JSON to `/v1/audio/speech`.
- Include `model`, `voice`, and `input`.
- Request `audio/wav`.
- Return raw audio bytes.

Native route:

- POST JSON to `/api/extra/tts`.
- Include `input`, `voice`, `instruction`, and optional `speaker_json`.
- Request `audio/wav`.
- Return raw audio bytes.

## Error Rules

- If required discovery metadata cannot be fetched, raise `KoboldCppDiscoveryError`.
- If a requested capability has no selected endpoint, raise `KoboldCppError`.
- Let HTTP errors from request methods surface as request exceptions for now; the app layer will later decide retry and recovery behavior.
- If TTS returns a non-audio response, accept base64 JSON audio fields before raising `KoboldCppError`.

## Tests

The adapter test suite must run offline with fake HTTP sessions.

Required coverage:

- `KoboldCppClient` satisfies `KoboldCppApi`.
- `KoboldCppProfile.to_dict()` is stable and sorted, and includes `context_limit_tokens`.
- Discovery extracts the context limit from `/api/extra/true_max_context_length` and
  from nested runtime metadata (e.g. `n_ctx`).
- Discovery prefers OpenAI-compatible routes when available.
- Discovery falls back to native routes when OpenAI-compatible routes are missing.
- Discovery marks explicitly disabled capabilities unavailable when no matching route exists.
- Chat request formatting is correct for OpenAI-compatible and native routes.
- Transcription request formatting is correct for OpenAI-compatible and native routes.
- TTS request formatting and audio parsing are correct for OpenAI-compatible and native routes.
- Unavailable endpoints raise `KoboldCppError`.
- Downstream STT, LLM, and TTS modules delegate through the adapter interface.
